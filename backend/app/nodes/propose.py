"""Node 2 — Propose. Claude drafts a bounded value-chain skeleton from recon."""
from __future__ import annotations

from .. import llm
from ..state import MarketMapState


def propose_node(state: MarketMapState) -> dict:
    attempt = state.get("propose_attempts", 0) + 1

    ue = state.get("user_edit") or {}
    rescope_notes = ue.get("notes", "") if ue.get("type") == "rescope_request" else ""

    proposal = llm.draft_proposal(
        topic=state["topic"],
        recon_results=state.get("recon_results", []),
        rescope_notes=rescope_notes,
        attempt=attempt,
    )
    return {"proposal": proposal, "propose_attempts": attempt}
