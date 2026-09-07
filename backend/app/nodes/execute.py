"""Node 4 — Execute. Per-layer company research, parallelised across layers.

Output per layer: candidate companies (name / URL / sources / tier-weighted
corroboration), plus meta (raw count, whether the query was reformulated,
whether the hard cap truncated the list).

Corroboration is tier-weighted here (edit c): a company with no tier1-3 source is
rejected outright; one that has tier1-3 sources but doesn't clear the threshold is
kept and flagged ``under_corroborated`` for the human to rescue in Synthesize.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Tuple

from .. import search, sources
from ..config import get_settings
from ..state import Company, MarketMapState
from ..utils import host_of


def _research_layer(
    topic: str,
    layer: str,
    definition: str,
    extra_by_tier: dict,
    threshold: float,
    hard_cap: int,
) -> Tuple[str, Dict[str, Any]]:
    found = search.find_company_sources(layer=layer, topic=topic, definition=definition)
    raw = found["candidates"]

    scored: List[Company] = []
    for c in raw:
        smeta = c.get("sources", [])
        assessed = sources.assess_sources(
            smeta,
            company_host=host_of(c["url"]),
            extra_by_tier=extra_by_tier,
            threshold=threshold,
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

    # Prefer the best-corroborated when a layer overflows the hard cap.
    scored.sort(key=lambda x: (-x["corroboration"]["score"], x["name"]))
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
                settings.corroboration_threshold,
                settings.layer_company_hard_cap,
            )
            for layer in layers
        ]
        for fut in futures:
            layer, result = fut.result()
            research[layer] = result["candidates"]
            layer_meta[layer] = result["meta"]

    return {"layer_research": research, "layer_meta": layer_meta}
