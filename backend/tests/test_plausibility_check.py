"""Plausibility check: a secondary, LLM-based sanity pass over companies that
already cleared the mechanical independent-source-count gate. Catches the
"content-farm swarm" failure mode a pure count-based rule can't (seen live at
real scale on SEO-adjacent topics). Must fail OPEN on any error -- it's a
bonus check, not the actual gate."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app import llm
from backend.app.config import Settings

STUB = Settings(use_stubs=True)
REAL = Settings(use_stubs=False, anthropic_api_key="x", exa_api_key="y")


def _candidates(*names):
    return [{"name": n, "sources": [{"url": f"https://{n}.example/a", "title": n}]} for n in names]


def test_stub_mode_passes_everything_through():
    out = llm.plausibility_check(_candidates("Acme", "Zeta"), topic="t", layer="L", definition="D", settings=STUB)
    assert out == {"Acme": True, "Zeta": True}


def test_empty_candidates_short_circuits():
    out = llm.plausibility_check([], topic="t", layer="L", definition="D", settings=REAL)
    assert out == {}


def test_real_mode_applies_model_verdicts(monkeypatch):
    monkeypatch.setattr(
        llm,
        "_json_call",
        lambda *a, **kw: {
            "verdicts": [
                {"name": "Acme", "plausible": True, "reason": "real coverage"},
                {"name": "Zeta", "plausible": False, "reason": "content-farm swarm"},
            ]
        },
    )
    out = llm.plausibility_check(_candidates("Acme", "Zeta"), topic="t", layer="L", definition="D", settings=REAL)
    assert out == {"Acme": True, "Zeta": False}


def test_missing_verdict_defaults_to_plausible(monkeypatch):
    monkeypatch.setattr(llm, "_json_call", lambda *a, **kw: {"verdicts": [{"name": "Acme", "plausible": False}]})
    out = llm.plausibility_check(_candidates("Acme", "Zeta"), topic="t", layer="L", definition="D", settings=REAL)
    assert out == {"Acme": False, "Zeta": True}  # Zeta got no verdict -> fail open


def test_model_error_fails_open_for_everyone(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(llm, "_json_call", boom)
    out = llm.plausibility_check(_candidates("Acme", "Zeta"), topic="t", layer="L", definition="D", settings=REAL)
    assert out == {"Acme": True, "Zeta": True}
