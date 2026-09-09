"""draft_proposal's real path must never hand back a Proposal missing a key --
a live run once got a Claude response with no `zoom_level` at all, which then
KeyError'd in run_local.py's display code with no defensive default anywhere
in between."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app import llm
from backend.app.config import Settings

REAL = Settings(use_stubs=False, anthropic_api_key="x", exa_api_key="y")

REQUIRED_KEYS = {
    "layers", "layer_definitions", "in_scope", "excluded_adjacent",
    "zoom_level", "open_questions", "notes",
}


def test_missing_zoom_level_is_defaulted_not_dropped(monkeypatch):
    monkeypatch.setattr(
        llm,
        "_json_call",
        lambda *a, **kw: {"layers": ["A", "B"], "layer_definitions": {"A": "a", "B": "b"}},
    )

    out = llm.draft_proposal(topic="t", recon_results=[], settings=REAL)
    assert REQUIRED_KEYS <= out.keys()
    assert out["zoom_level"] == "company"
    assert out["layers"] == ["A", "B"]  # keys the model DID supply are untouched


def test_fully_populated_response_is_passed_through_unchanged(monkeypatch):
    full = {
        "layers": ["A"],
        "layer_definitions": {"A": "a"},
        "in_scope": ["x"],
        "excluded_adjacent": ["y"],
        "zoom_level": "category",
        "open_questions": ["q?"],
        "notes": "n",
    }
    monkeypatch.setattr(llm, "_json_call", lambda *a, **kw: dict(full))

    out = llm.draft_proposal(topic="t", recon_results=[], settings=REAL)
    assert out == full
