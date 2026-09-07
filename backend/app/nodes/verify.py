"""Node 5 — Verify + populate. Two separate checks per company.

  1. Existence & identity  — URL actually resolves; write a grounded one-liner.
  2. Category fit           — one-liner vs the layer's confirmed definition.

Nothing is silently dropped: a failed check sets ``rejection_reason`` and the
company is carried through so Synthesize can list it with a stated reason.
"""
from __future__ import annotations

from typing import Dict, List

from .. import llm, search
from ..state import Company, MarketMapState


def verify_node(state: MarketMapState) -> dict:
    scope = state["confirmed_scope"]
    defs: Dict[str, str] = scope.get("layer_definitions", {})
    research: Dict[str, List[Company]] = state.get("layer_research", {})

    verified: Dict[str, List[Company]] = {}
    for layer, cands in research.items():
        checked: List[Company] = []
        for c in cands:
            # Already failed the corroboration bar in Execute — keep as-is.
            if c.get("rejection_reason"):
                checked.append(c)
                continue

            # (1) existence & identity
            res = search.resolve_url(c["url"])
            if not res.get("resolves"):
                c["rejection_reason"] = (
                    f"failed_existence: URL did not resolve ({res.get('status')})"
                )
                checked.append(c)
                continue
            c["url"] = res.get("final_url", c["url"])
            c["one_liner"] = llm.company_one_liner(
                c["name"],
                c["url"],
                evidence=c.get("sources", []),
                layer=layer,
                layer_definition=defs.get(layer, ""),
            )

            # (2) category fit
            fits, why = llm.category_fit(
                c["one_liner"],
                layer,
                defs.get(layer, ""),
                miscategorized_hint=c.get("_miscategorized", False),
            )
            c["category_fit"] = fits
            if not fits:
                c["rejection_reason"] = f"failed_category_fit: {why}"
            else:
                # Passed existence + category fit. Corroboration strength
                # (corroboration.status) is assessed in Execute; Synthesize routes
                # under-corroborated-but-verified companies to needs_review.
                c["verified"] = True

            checked.append(c)
        verified[layer] = checked

    return {"layer_research": verified}
