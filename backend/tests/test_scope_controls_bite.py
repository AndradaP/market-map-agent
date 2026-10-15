"""The confirm screen's parameters have to reach the pipeline, or they're
decorative controls that lie to the user.

Found by reading the code during the UX rework: `in_scope` /
`excluded_adjacent` were never referenced by execute.py or verify.py at
all (they only shaped explanation prose), and breadth was the global
constant `layer_company_hard_cap`, identical for every layer and
untouchable from the proposal. So the model could ask "are hyperscalers in
scope?" or "how wide should this layer go?", the user could answer, and
the map came out the same either way. These tests pin the wiring.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app import llm, search
from backend.app.nodes import execute as execute_mod
from backend.app.nodes import verify as verify_mod

SCOPE = {
    "layers": ["Storage"],
    "layer_definitions": {"Storage": "Backends that persist traces."},
    "in_scope": ["LLM tracing"],
    "excluded_adjacent": ["generic APM"],
    "zoom_level": "company",
    "companies_per_layer": 10,
    "guidance": "European players only",
}


def test_breadth_comes_from_the_scope_not_the_global_constant(monkeypatch):
    seen = {}

    def _fake_layer(topic, layer, definition, extra, hard_cap, settings, guidance=""):
        seen["hard_cap"] = hard_cap
        seen["guidance"] = guidance
        return layer, {"candidates": [], "meta": {}}

    monkeypatch.setattr(execute_mod, "_research_layer", _fake_layer)
    execute_mod.execute_node({"topic": "t", "confirmed_scope": SCOPE})

    assert seen["hard_cap"] == 10, "per-map breadth must override layer_company_hard_cap"
    assert seen["guidance"] == "European players only"


def test_missing_breadth_falls_back_to_the_configured_default(monkeypatch):
    # A confirm-as-is or an older client that never sends the field must not
    # reach Execute with None and cap every layer at zero companies.
    seen = {}

    def _fake_layer(topic, layer, definition, extra, hard_cap, settings, guidance=""):
        seen["hard_cap"] = hard_cap
        return layer, {"candidates": [], "meta": {}}

    monkeypatch.setattr(execute_mod, "_research_layer", _fake_layer)
    bare = {k: v for k, v in SCOPE.items() if k != "companies_per_layer"}
    execute_mod.execute_node({"topic": "t", "confirmed_scope": bare})

    assert seen["hard_cap"] > 0


def test_guidance_reaches_the_search_query(monkeypatch):
    queries = []
    monkeypatch.setattr(
        search, "web_search", lambda q, num_results=10, settings=None: queries.append(q) or []
    )
    monkeypatch.setattr(search, "reformulate_query", lambda *a, **kw: "broadened")
    from backend.app.config import Settings

    real = Settings(use_stubs=False, anthropic_api_key="x", exa_api_key="y", database_url="")
    search.find_company_sources(
        layer="Storage", topic="observability", definition="d",
        guidance="European players only", settings=real,
    )

    assert any("European players only" in q for q in queries)


def test_scope_boundaries_and_guidance_reach_the_category_fit_check(monkeypatch):
    seen = {}

    def _fake_fit(one_liner, layer, definition, **kw):
        seen.update(kw)
        return True, "ok"

    monkeypatch.setattr(verify_mod.llm, "category_fit", _fake_fit)
    monkeypatch.setattr(verify_mod.llm, "company_one_liner", lambda *a, **kw: "a one-liner")
    monkeypatch.setattr(
        verify_mod.search, "resolve_url", lambda url: {"resolves": True, "final_url": url}
    )

    verify_mod.verify_node(
        {
            "confirmed_scope": SCOPE,
            "layer_research": {
                "Storage": [{"name": "Acme", "url": "https://acme.com", "sources": []}]
            },
        }
    )

    assert seen["in_scope"] == ["LLM tracing"]
    assert seen["excluded"] == ["generic APM"]
    assert seen["guidance"] == "European players only"


def test_category_fit_prompt_states_the_boundaries_as_binding(monkeypatch):
    captured = {}

    def _fake_call(settings, *, model, system, user):
        captured["system"] = system
        captured["user"] = user
        return {"fits": False, "reason": "excluded"}

    monkeypatch.setattr(llm, "_json_call", _fake_call)
    from backend.app.config import Settings

    real = Settings(use_stubs=False, anthropic_api_key="x", exa_api_key="y", database_url="")
    fits, _ = llm.category_fit(
        "a generic APM vendor", "Storage", "Backends that persist traces.",
        in_scope=["LLM tracing"], excluded=["generic APM"],
        guidance="European players only", settings=real,
    )

    assert fits is False
    assert "generic APM" in captured["user"]
    assert "European players only" in captured["user"]
    assert "binding" in captured["system"]
