"""Node 1 — Recon. Broad web search on the topic as given, no scoping yet."""
from __future__ import annotations

from .. import llm, search
from ..state import MarketMapState


def recon_node(state: MarketMapState) -> dict:
    topic = state["topic"]

    # Reuse guard: only re-run a fresh search when the user explicitly flagged
    # "this is actually a different topic". Normal rescopes route straight to
    # Propose and reuse these results.
    ue = state.get("user_edit") or {}
    if state.get("recon_results") and not ue.get("different_topic"):
        return {}

    queries = llm.recon_queries(topic)
    seen, results = set(), []
    for q in queries:
        for hit in search.web_search(q, num_results=6):
            if hit["url"] in seen:
                continue
            seen.add(hit["url"])
            results.append({**hit, "query": q})

    # Recon also names the credible outlets for THIS topic (tier 1/2/3), which
    # Execute/Verify use for corroboration instead of a fixed per-vertical list.
    outlets = llm.credible_outlets(topic, results)

    return {"recon_results": results, "credible_outlets": outlets}
