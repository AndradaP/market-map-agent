"""Rescope cap logic — the one piece of control flow that must be exactly right."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from backend.app.graph import build_graph, route_after_confirm
from backend.app.nodes.confirm import looks_like_direct_edit, note_is_actionable

TOPIC = "AI observability"
# An actionable note: long, names a boundary concern -> granted without a clarification round.
RESCOPE = {
    "type": "rescope_request",
    "notes": "the layers are too broad; please split storage from instrumentation",
    "different_topic": False,
    "edited_scope": None,
}
CONFIRM = {"type": "none", "notes": "", "different_topic": False, "edited_scope": None}


def _review(result):
    intr = result.get("__interrupt__")
    return getattr(intr[0], "value", intr[0]) if intr else None


def _new():
    graph = build_graph(MemorySaver())
    cfg = {"configurable": {"thread_id": "t"}}
    return graph, cfg


def test_two_rescopes_then_forced_direct_edit():
    graph, cfg = _new()
    r = graph.invoke({"topic": TOPIC, "run_id": "t"}, cfg)
    assert _review(r)["rescopes_remaining"] == 2

    r = graph.invoke(Command(resume=RESCOPE), cfg)
    assert _review(r)["rescopes_remaining"] == 1
    assert _review(r)["direct_edit_only"] is False

    r = graph.invoke(Command(resume=RESCOPE), cfg)
    assert _review(r)["rescopes_remaining"] == 0
    assert _review(r)["direct_edit_only"] is False  # cap not yet exceeded

    # 3rd request is refused: still paused, now direct-edit-only, handoff stated.
    r = graph.invoke(Command(resume=RESCOPE), cfg)
    review = _review(r)
    assert review is not None
    assert review["direct_edit_only"] is True
    assert "over to you" in review["handoff_message"].lower()


def test_propose_runs_at_most_three_times():
    graph, cfg = _new()
    graph.invoke({"topic": TOPIC, "run_id": "t"}, cfg)
    graph.invoke(Command(resume=RESCOPE), cfg)
    graph.invoke(Command(resume=RESCOPE), cfg)
    r = graph.invoke(Command(resume=RESCOPE), cfg)  # refused
    assert _review(r)["attempt"] == 3  # 1 initial + 2 rescopes, no 4th

    r = graph.invoke(Command(resume=CONFIRM), cfg)  # confirm the last proposal
    assert r["metrics"]["rescope_count"] == 2
    assert r["metrics"]["cap_hit"] is True


def test_confirm_immediately_completes():
    graph, cfg = _new()
    graph.invoke({"topic": TOPIC, "run_id": "t"}, cfg)
    r = graph.invoke(Command(resume=CONFIRM), cfg)
    assert r["final_output"]["topic"] == TOPIC
    assert r["metrics"]["rescope_count"] == 0
    assert r["metrics"]["cap_hit"] is False


def test_thin_rescope_gets_one_free_clarification_round():
    graph, cfg = _new()
    graph.invoke({"topic": TOPIC, "run_id": "t"}, cfg)

    # A thin note -> the gate asks a question instead of spending an attempt.
    r = graph.invoke(
        Command(resume={"type": "rescope_request", "notes": "meh", "different_topic": False}), cfg
    )
    review = _review(r)
    assert review["kind"] == "rescope_clarification"
    assert review["question"]

    # Answering routes back to Propose and only now spends the attempt.
    r = graph.invoke(
        Command(resume={"type": "rescope_clarification", "notes": "split storage from instrumentation"}),
        cfg,
    )
    review = _review(r)
    assert review["kind"] == "proposal_review"
    assert review["rescopes_used"] == 1
    assert review["attempt"] == 2


def test_note_heuristics():
    layers = ["Instrumentation & SDKs", "Trace & Span Storage"]
    assert note_is_actionable("split Trace & Span Storage into two", layers, 15) is True
    assert note_is_actionable("this should be broader in scope please", layers, 15) is True
    assert note_is_actionable("meh", layers, 15) is False
    assert note_is_actionable("no good", layers, 15) is False
    assert looks_like_direct_edit("please rename Trace & Span Storage", layers) is True
    assert looks_like_direct_edit("it feels wrong somehow", layers) is False


def test_router_matrix():
    assert route_after_confirm({"user_edit": {"type": "none"}}) == "execute"
    assert route_after_confirm({"user_edit": {"type": "direct_edit"}}) == "execute"
    assert route_after_confirm({"user_edit": {"type": "rescope_request"}}) == "propose"
    assert (
        route_after_confirm({"user_edit": {"type": "rescope_request", "different_topic": True}})
        == "recon"
    )
    assert (
        route_after_confirm({"user_edit": {"type": "rescope_request"}, "cap_hit": True}) == "confirm"
    )
