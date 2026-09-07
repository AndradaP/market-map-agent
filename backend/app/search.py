"""Exa calls: recon search, per-layer company discovery, URL verification.
Stub fallbacks keep the graph runnable offline.
"""
from __future__ import annotations

from typing import List, Optional

from langsmith import traceable

from . import stubs
from .config import Settings, get_settings

_exa_cache = {}


def _exa(settings: Settings):
    if "e" not in _exa_cache:
        from exa_py import Exa

        _exa_cache["e"] = Exa(settings.exa_api_key)
    return _exa_cache["e"]


@traceable(run_type="retriever", name="exa.web_search")
def web_search(query: str, *, num_results: int = 8, settings: Optional[Settings] = None) -> List[dict]:
    settings = settings or get_settings()
    if settings.stubs_enabled:
        return stubs.web_search(query, num_results=num_results)
    res = _exa(settings).search_and_contents(
        query, num_results=num_results, type="auto", text={"max_characters": 1200}
    )
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


def _group_hits_to_candidates(hits: List[dict]) -> List[dict]:
    from .utils import host_of

    grouped: dict = {}
    for h in hits:
        host = host_of(h["url"])
        if not host:
            continue
        grouped.setdefault(host, {"name": host, "url": f"https://{host}", "sources": []})
        grouped[host]["sources"].append({"url": h["url"], "title": h.get("title", "")})
    return [g for g in grouped.values() if g["sources"]]


@traceable(run_type="retriever", name="exa.find_company_sources")
def find_company_sources(
    *, layer: str, topic: str, definition: str, settings: Optional[Settings] = None
) -> dict:
    """Return ``{candidates: [...], reformulated: bool}``.

    If the first search comes back empty, the query is reformulated once and
    retried before the layer is declared empty (edit d).
    """
    settings = settings or get_settings()

    if settings.stubs_enabled:
        cands = stubs.company_candidates(topic, layer, definition, attempt=1)
        if cands:
            return {"candidates": cands, "reformulated": False}
        cands = stubs.company_candidates(topic, layer, definition, attempt=2)
        return {"candidates": cands, "reformulated": True}

    # Real path (skeleton): search, group hits by domain as naive "candidates".
    # Production would add an LLM extraction pass to pull real company names + URLs,
    # then re-search each name for corroboration.
    q = f'"{topic}" "{layer}" companies vendors players'
    hits = web_search(q, num_results=15, settings=settings)
    reformulated = False
    if not hits:
        hits = web_search(reformulate_query(q), num_results=15, settings=settings)
        reformulated = True
    return {"candidates": _group_hits_to_candidates(hits), "reformulated": reformulated}


@traceable(name="exa.resolve_url")
def resolve_url(url: str, *, settings: Optional[Settings] = None) -> dict:
    """{resolves: bool, final_url: str, status: int} — used by Verify for the
    existence/identity check. A fabricated-looking URL that doesn't resolve is
    worse than no URL, so this is a hard gate."""
    settings = settings or get_settings()
    if settings.stubs_enabled:
        return stubs.resolve_url(url)
    import httpx

    try:
        r = httpx.head(url, follow_redirects=True, timeout=8.0)
        if r.status_code >= 400 or r.status_code == 405:
            r = httpx.get(url, follow_redirects=True, timeout=10.0)
        return {"resolves": r.status_code < 400, "final_url": str(r.url), "status": r.status_code}
    except Exception as exc:  # noqa: BLE001
        return {"resolves": False, "final_url": url, "status": 0, "error": str(exc)}
