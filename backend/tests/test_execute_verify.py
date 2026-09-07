"""Execute + Verify + Synthesize behaviour: reformulation, hard cap, and the
verified-but-under-corroborated review queue. All via stubs (deterministic)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from backend.app.graph import build_graph
from backend.app.search import reformulate_query

CONFIRM = {"type": "none", "notes": "", "different_topic": False, "edited_scope": None}


def _run(topic="AI observability"):
    graph = build_graph(MemorySaver())
    cfg = {"configurable": {"thread_id": "x"}}
    graph.invoke({"topic": topic, "run_id": "x"}, cfg)
    return graph.invoke(Command(resume=CONFIRM), cfg)


def test_reformulate_query_broadens():
    out = reformulate_query('"AI observability" "Storage" companies vendors')
    assert '"' not in out
    assert "companies" not in out
    assert "OR" in out


def test_sparse_layer_is_recovered_by_reformulation():
    final = _run()["final_output"]
    mon = next(l for l in final["layers"] if l["name"].startswith("Monitoring"))
    assert mon["reformulated"] is True
    assert mon["status"] == "ok"  # empty on first search, populated on retry
    assert len(mon["companies"]) >= 1


def test_under_corroborated_company_goes_to_review_queue_not_the_map():
    final = _run()["final_output"]
    review_names = {c["name"] for c in final["needs_review"]}
    assert "Langfuse" in review_names  # 1 tier-3 source + existence-only -> under-corroborated
    on_map = {c["name"] for layer in final["layers"] for c in layer["companies"]}
    assert "Langfuse" not in on_map


def test_corroborated_companies_carry_tier_spread():
    final = _run()["final_output"]
    langsmith = next(
        c for layer in final["layers"] for c in layer["companies"] if c["name"] == "LangSmith"
    )
    assert langsmith["corroboration"]["status"] == "corroborated"
    assert langsmith["corroboration"]["tiers"]  # non-empty tier list
    assert langsmith["corroboration"]["score"] >= 3.0


def test_metrics_expose_new_counters():
    m = _run()["metrics"]
    for k in (
        "companies_under_corroborated",
        "layers_reformulated",
        "layers_over_cap",
        "rejected_failed_existence",
    ):
        assert k in m
    assert m["layers_reformulated"] >= 1
    assert m["companies_under_corroborated"] >= 1
