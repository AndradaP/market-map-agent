"""The loop. START -> recon -> propose -> confirm (interrupt) -> execute -> verify
-> synthesize -> END, with the rescope back-edge out of confirm.
"""
from __future__ import annotations

from typing import Optional

from langgraph.graph import END, START, StateGraph

from .nodes import (
    confirm_node,
    execute_node,
    propose_node,
    recon_node,
    synthesize_node,
    verify_node,
)
from .state import MarketMapState

# Route targets out of the confirm gate.
_TO_RECON = "recon"
_TO_PROPOSE = "propose"
_TO_CONFIRM = "confirm"
_TO_EXECUTE = "execute"


def route_after_confirm(state: MarketMapState) -> str:
    ue = state.get("user_edit") or {}
    etype = ue.get("type", "none")

    if etype == "rescope_request":
        if state.get("cap_hit"):
            # Cap reached this pass — re-show the proposal in direct-edit-only mode.
            return _TO_CONFIRM
        # Granted rescope: fresh recon only if the user ticked "different topic".
        return _TO_RECON if ue.get("different_topic") else _TO_PROPOSE

    # "none" (confirm as-is) or "direct_edit" -> scope is locked, proceed.
    return _TO_EXECUTE


def build_graph(checkpointer=None):
    if checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()

    b = StateGraph(MarketMapState)
    b.add_node(_TO_RECON, recon_node)
    b.add_node(_TO_PROPOSE, propose_node)
    b.add_node(_TO_CONFIRM, confirm_node)
    b.add_node(_TO_EXECUTE, execute_node)
    b.add_node("verify", verify_node)
    b.add_node("synthesize", synthesize_node)

    b.add_edge(START, _TO_RECON)
    b.add_edge(_TO_RECON, _TO_PROPOSE)
    b.add_edge(_TO_PROPOSE, _TO_CONFIRM)
    b.add_conditional_edges(
        _TO_CONFIRM,
        route_after_confirm,
        {
            _TO_RECON: _TO_RECON,
            _TO_PROPOSE: _TO_PROPOSE,
            _TO_CONFIRM: _TO_CONFIRM,
            _TO_EXECUTE: _TO_EXECUTE,
        },
    )
    b.add_edge(_TO_EXECUTE, "verify")
    b.add_edge("verify", "synthesize")
    b.add_edge("synthesize", END)

    return b.compile(checkpointer=checkpointer)
