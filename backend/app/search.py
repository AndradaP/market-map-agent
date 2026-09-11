"""Exa calls: recon search, per-layer company discovery, URL verification.
Stub fallbacks keep the graph runnable offline.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import httpx
from langsmith import traceable
from tenacity import (
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from . import llm, stubs
from .config import Settings, get_settings

_exa_cache = {}


def _exa(settings: Settings):
    if "e" not in _exa_cache:
        from exa_py import Exa

        _exa_cache["e"] = Exa(settings.exa_api_key.get_secret_value() if settings.exa_api_key else None)
    return _exa_cache["e"]


def _is_rate_limit(exc: BaseException) -> bool:
    # exa_py raises a bare ValueError for every non-2xx response; the status
    # code/tag are only in the message, not a distinct exception type.
    msg = str(exc).upper()
    return "429" in msg or "RATE_LIMIT" in msg


@retry(
    retry=retry_if_exception(_is_rate_limit),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    reraise=True,
)
def _exa_search_and_contents(settings: Settings, query: str, *, num_results: int):
    # Real Execute fans out per-layer AND per-company concurrently (see
    # execute.py / find_company_sources' ThreadPoolExecutors), which can burst
    # well past Exa's per-second rate limit even at modest worker counts.
    # Retry-with-backoff absorbs that instead of crashing the whole run.
    return _exa(settings).search_and_contents(
        query, num_results=num_results, type="auto", text={"max_characters": 1200}
    )


@traceable(run_type="retriever", name="exa.web_search")
def web_search(query: str, *, num_results: int = 8, settings: Optional[Settings] = None) -> List[dict]:
    settings = settings or get_settings()
    if settings.stubs_enabled:
        return stubs.web_search(query, num_results=num_results)
    res = _exa_search_and_contents(settings, query, num_results=num_results)
    return [
        {
            "title": r.title,
            "url": r.url,
            "text": getattr(r, "text", "") or "",
            "published_date": getattr(r, "published_date", None),
        }
        for r in res.results
    ]


def reformulate_query(query: str) -> str:
    """Broaden a query that returned nothing: drop quoted phrases, widen the verb set."""
    q = query.replace('"', " ")
    q = " ".join(q.split())
    for noun in ("companies", "vendors", "players", "suppliers", "startups"):
        q = q.replace(f" {noun}", "")
    return f"{q.strip()} vendors OR suppliers OR startups OR providers"


def _mentions(hit: dict, name: str) -> bool:
    """Cheap check: does this hit's own title actually name the company? Used to
    credit the hit that surfaced a company as one of its sources too, on top of
    the dedicated corroboration search below."""
    return bool(name.strip()) and name.strip().lower() in (hit.get("title") or "").lower()


def _dedupe_by_url(*groups: List[dict]) -> List[dict]:
    seen = set()
    out: List[dict] = []
    for g in groups:
        for s in g:
            u = s.get("url") if isinstance(s, dict) else s
            if u and u not in seen:
                seen.add(u)
                out.append(s)
    return out


@traceable(run_type="retriever", name="exa.corroborate_company")
def corroborate_company(
    name: str, topic: str, *, num_results: int, settings: Optional[Settings] = None
) -> List[dict]:
    """Independent search for one already-extracted company — this is what makes
    corroboration real: sources that cover the company on their own, not sources
    that merely happened to share a search hit with it."""
    hits = web_search(f'"{name}" {topic}', num_results=num_results, settings=settings)
    return [{"url": h["url"], "title": h.get("title", "")} for h in hits]


@traceable(run_type="retriever", name="exa.find_company_sources")
def find_company_sources(
    *, layer: str, topic: str, definition: str, settings: Optional[Settings] = None
) -> dict:
    """Return ``{candidates: [...], reformulated: bool}``.

    If the first search comes back empty, the query is reformulated once and
    retried before the layer is declared empty (edit d).

    Real path: search the layer -> LLM-extract a deduped company list from ALL
    hits together (a hit can name several companies; a company can recur across
    hits) -> one independent corroboration search per company, run in parallel,
    plus credit for whichever original hit(s) actually named it.
    """
    settings = settings or get_settings()

    if settings.stubs_enabled:
        cands = stubs.company_candidates(topic, layer, definition, attempt=1)
        if cands:
            return {"candidates": cands, "reformulated": False}
        cands = stubs.company_candidates(topic, layer, definition, attempt=2)
        return {"candidates": cands, "reformulated": True}

    q = f'"{topic}" "{layer}" companies vendors players'
    hits = web_search(q, num_results=15, settings=settings)
    reformulated = False
    if not hits:
        hits = web_search(reformulate_query(q), num_results=15, settings=settings)
        reformulated = True
    if not hits:
        return {"candidates": [], "reformulated": reformulated}

    extracted = llm.extract_companies(
        hits,
        topic=topic,
        layer=layer,
        definition=definition,
        cap=settings.layer_extract_cap,
        settings=settings,
    )
    if not extracted:
        return {"candidates": [], "reformulated": reformulated}

    with ThreadPoolExecutor(max_workers=min(settings.company_corroboration_workers, len(extracted))) as pool:
        future_to_company = {
            pool.submit(
                corroborate_company,
                c["name"],
                topic,
                num_results=settings.company_corroboration_results,
                settings=settings,
            ): c
            for c in extracted
        }
        candidates = []
        for fut, c in future_to_company.items():
            origin_sources = [
                {"url": h["url"], "title": h.get("title", "")} for h in hits if _mentions(h, c["name"])
            ]
            candidates.append(
                {
                    "name": c["name"],
                    "url": c["url"],
                    "sources": _dedupe_by_url(origin_sources, fut.result()),
                }
            )

    return {"candidates": candidates, "reformulated": reformulated}


# Real, bot-protected company sites (Cloudflare and similar WAFs) 403 the
# default httpx client outright — no browser-shaped User-Agent, no admission.
# Without this, a genuinely real company like openai.com fails "existence".
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


@retry(
    retry=retry_if_exception_type(httpx.TransportError),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    reraise=True,
)
def _fetch(url: str):
    r = httpx.head(url, headers=_BROWSER_HEADERS, follow_redirects=True, timeout=8.0)
    if r.status_code >= 400 or r.status_code == 405:
        r = httpx.get(url, headers=_BROWSER_HEADERS, follow_redirects=True, timeout=10.0)
    return r


@traceable(name="exa.resolve_url")
def resolve_url(url: str, *, settings: Optional[Settings] = None) -> dict:
    """{resolves: bool, final_url: str, status: int} — used by Verify for the
    existence/identity check. A fabricated-looking URL that doesn't resolve is
    worse than no URL, so this is a hard gate.

    One retry absorbs plain network flakiness (seen live: the identical URL,
    modulo a www./trailing-slash cosmetic difference, resolved fine twice in
    one run and failed with a bare connection error the third time). `status`
    is returned as-is on a real HTTP response (including 403/429) so Verify
    can weigh an ambiguous bot-block differently from a hard failure, rather
    than that policy call being made here.
    """
    settings = settings or get_settings()
    if settings.stubs_enabled:
        return stubs.resolve_url(url)

    try:
        r = _fetch(url)
        return {"resolves": r.status_code < 400, "final_url": str(r.url), "status": r.status_code}
    except Exception as exc:  # noqa: BLE001
        return {"resolves": False, "final_url": url, "status": 0, "error": str(exc)}
