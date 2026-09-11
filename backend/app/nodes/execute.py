"""Node 4 — Execute. Per-layer company research, parallelised across layers.

Output per layer: candidate companies (name / URL / sources / corroboration),
plus meta (raw count, whether the query was reformulated, whether the hard cap
truncated the list).

Corroboration gates on independent source *count*, not a curated credibility
tier (see sources.assess_sources): a company with zero independent, non-junk
sources is rejected outright; one with exactly one is kept and flagged
``under_corroborated`` for the human to rescue in Synthesize.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Tuple

from .. import llm, registry, search, sources
from ..config import Settings, get_settings
from ..state import Company, MarketMapState
from ..utils import host_of

_STATUS_RANK = {"corroborated": 0, "under_corroborated": 1, "uncorroborated": 2}


def _research_layer(
    topic: str,
    layer: str,
    definition: str,
    extra_by_tier: dict,
    hard_cap: int,
    settings: Settings,
) -> Tuple[str, Dict[str, Any]]:
    found = search.find_company_sources(
        layer=layer, topic=topic, definition=definition, settings=settings
    )
    raw = found["candidates"]

    scored: List[Company] = []
    kept_sources_by_name: Dict[str, list] = {}
    for c in raw:
        canonical_name, smeta = registry.merge_and_store(
            name=c["name"],
            url=c["url"],
            new_sources=c.get("sources", []),
            topic=topic,
            settings=settings,
        )
        c = {**c, "name": canonical_name}
        assessed = sources.assess_sources(
            smeta,
            company_host=host_of(c["url"]),
            extra_by_tier=extra_by_tier,
        )
        cand: Company = {
            "name": c["name"],
            "url": c["url"],
            "sources": [s["url"] if isinstance(s, dict) else str(s) for s in smeta],
            "one_liner": "",
            "verified": False,
            "category_fit": False,
            "corroboration": {
                "status": assessed["status"],
                "independent_hosts": assessed["independent_hosts"],
                "score": assessed["score"],
                "tiers": assessed["tiers"],
                "detail": assessed["detail"],
            },
            "rejection_reason": (
                f"failed_corroboration: {assessed['detail']}"
                if assessed["status"] == "uncorroborated"
                else None
            ),
            # deterministic hint for the stub category-fit check; ignored by the real path
            "_miscategorized": c.get("_miscategorized", False),
        }
        scored.append(cand)
        kept_sources_by_name[c["name"]] = assessed["kept_sources"]

    # Mechanical count-gate can't tell a real niche newsletter from a swarm of
    # small, generically-named content-farm sites blogging the same generic
    # topic (seen live, at real scale, for SEO-adjacent topics). One cheap LLM
    # sanity pass over just the already-corroborated shortlist -- not every
    # candidate -- catches that without reintroducing a curated-outlet list.
    passed = [c for c in scored if c["corroboration"]["status"] == "corroborated"]
    if passed:
        verdicts = llm.plausibility_check(
            [{"name": c["name"], "sources": kept_sources_by_name[c["name"]]} for c in passed],
            topic=topic,
            layer=layer,
            definition=definition,
            settings=settings,
        )
        for c in passed:
            if not verdicts.get(c["name"], True):
                c["corroboration"]["status"] = "under_corroborated"
                c["corroboration"]["detail"] = (
                    f"{c['corroboration']['detail']} — flagged: sources read as generic "
                    "content-farm coverage, not substantive independent reporting"
                )

    # Prefer the best-corroborated when a layer overflows the hard cap: status
    # first (corroborated beats under-corroborated regardless of tier score),
    # then independent-source count, then the tier-weighted score as a
    # display-quality tiebreak among otherwise-equal candidates.
    scored.sort(
        key=lambda x: (
            _STATUS_RANK[x["corroboration"]["status"]],
            -len(x["corroboration"]["independent_hosts"]),
            -x["corroboration"]["score"],
            x["name"],
        )
    )
    raw_count = len(scored)
    kept = scored[:hard_cap]

    meta = {
        "raw_count": raw_count,
        "reformulated": found["reformulated"],
        "over_cap": raw_count > hard_cap,
    }
    return layer, {"candidates": kept, "meta": meta}


def execute_node(state: MarketMapState) -> dict:
    settings = get_settings()
    topic = state["topic"]
    scope = state["confirmed_scope"]
    layers: List[str] = scope.get("layers", [])
    defs: Dict[str, str] = scope.get("layer_definitions", {})
    extra_by_tier: dict = state.get("credible_outlets", {}) or {}

    research: Dict[str, List[Company]] = {}
    layer_meta: Dict[str, Any] = {}
    if not layers:
        return {"layer_research": research, "layer_meta": layer_meta}

    with ThreadPoolExecutor(max_workers=min(6, len(layers))) as pool:
        futures = [
            pool.submit(
                _research_layer,
                topic,
                layer,
                defs.get(layer, ""),
                extra_by_tier,
                settings.layer_company_hard_cap,
                settings,
            )
            for layer in layers
        ]
        for fut in futures:
            layer, result = fut.result()
            research[layer] = result["candidates"]
            layer_meta[layer] = result["meta"]

    return {"layer_research": research, "layer_meta": layer_meta}
