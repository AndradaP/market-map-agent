"""Real (non-stub) Execute path: search -> LLM extraction -> per-company
corroboration search. Every external call (Exa search, Claude extraction) is
monkeypatched, so this needs no network and no API key even though it exercises
the stubs_enabled=False branch."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app import llm, search
from backend.app.config import Settings

REAL = Settings(use_stubs=False, anthropic_api_key="x", exa_api_key="y")


def _roundup(*names: str) -> list:
    """One search hit whose title names every company in `names` — the
    "one link surfaces several companies" case."""
    return [
        {
            "title": "Top tools: " + ", ".join(names),
            "url": "https://trade-press.example.com/roundup",
            "text": f"A roundup covering {', '.join(names)}.",
            "published_date": None,
        }
    ]


def test_one_hit_can_surface_multiple_companies(monkeypatch):
    monkeypatch.setattr(search, "web_search", lambda q, **kw: _roundup("Acme", "Zeta"))
    monkeypatch.setattr(
        llm,
        "extract_companies",
        lambda hits, **kw: [
            {"name": "Acme", "url": "https://acme.com"},
            {"name": "Zeta", "url": "https://zeta.com"},
        ],
    )
    monkeypatch.setattr(search, "corroborate_company", lambda name, topic, **kw: [])

    out = search.find_company_sources(layer="L", topic="T", definition="D", settings=REAL)
    assert {c["name"] for c in out["candidates"]} == {"Acme", "Zeta"}


def test_corroboration_runs_once_per_extracted_company_in_parallel(monkeypatch):
    calls = []

    def fake_corroborate(name, topic, **kw):
        calls.append(name)
        return [{"url": f"https://press.example/{name}", "title": name}]

    monkeypatch.setattr(search, "web_search", lambda q, **kw: _roundup("Acme"))
    monkeypatch.setattr(
        llm, "extract_companies", lambda hits, **kw: [{"name": "Acme", "url": "https://acme.com"}]
    )
    monkeypatch.setattr(search, "corroborate_company", fake_corroborate)

    out = search.find_company_sources(layer="L", topic="T", definition="D", settings=REAL)
    assert calls == ["Acme"]
    urls = {s["url"] for s in out["candidates"][0]["sources"]}
    assert "https://press.example/Acme" in urls


def test_origin_hit_that_names_the_company_is_credited_as_a_source(monkeypatch):
    # Dedicated corroboration search comes back empty; the origin hit should
    # still be kept, since it genuinely named the company.
    monkeypatch.setattr(search, "web_search", lambda q, **kw: _roundup("Acme"))
    monkeypatch.setattr(
        llm, "extract_companies", lambda hits, **kw: [{"name": "Acme", "url": "https://acme.com"}]
    )
    monkeypatch.setattr(search, "corroborate_company", lambda name, topic, **kw: [])

    out = search.find_company_sources(layer="L", topic="T", definition="D", settings=REAL)
    urls = {s["url"] for s in out["candidates"][0]["sources"]}
    assert "https://trade-press.example.com/roundup" in urls


def test_no_hits_after_reformulation_skips_extraction_entirely(monkeypatch):
    monkeypatch.setattr(search, "web_search", lambda q, **kw: [])
    called = []
    monkeypatch.setattr(llm, "extract_companies", lambda *a, **kw: called.append(1))

    out = search.find_company_sources(layer="L", topic="T", definition="D", settings=REAL)
    assert out == {"candidates": [], "reformulated": True}
    assert called == []


def test_extraction_is_called_with_the_configured_cap(monkeypatch):
    captured = {}

    def fake_extract(hits, *, cap, **kw):
        captured["cap"] = cap
        return []

    monkeypatch.setattr(search, "web_search", lambda q, **kw: _roundup("Acme"))
    monkeypatch.setattr(llm, "extract_companies", fake_extract)

    out = search.find_company_sources(layer="L", topic="T", definition="D", settings=REAL)
    assert captured["cap"] == REAL.layer_extract_cap
    assert out == {"candidates": [], "reformulated": False}


def test_corroboration_uses_the_configured_result_count(monkeypatch):
    captured = {}

    def fake_corroborate(name, topic, *, num_results, **kw):
        captured["num_results"] = num_results
        return []

    monkeypatch.setattr(search, "web_search", lambda q, **kw: _roundup("Acme"))
    monkeypatch.setattr(
        llm, "extract_companies", lambda hits, **kw: [{"name": "Acme", "url": "https://acme.com"}]
    )
    monkeypatch.setattr(search, "corroborate_company", fake_corroborate)

    search.find_company_sources(layer="L", topic="T", definition="D", settings=REAL)
    assert captured["num_results"] == REAL.company_corroboration_results
