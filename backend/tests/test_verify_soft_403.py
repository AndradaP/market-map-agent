"""A 403/429 on existence-check means the site is there but blocking automated
access, not "this doesn't exist" -- seen live: a strongly-corroborated real
company (Fervo Energy: techcrunch, wikipedia, cnbc, newsweek) got hard-rejected
purely because its site's WAF blocks a plain HTTP client. verify_node must not
let that override real independent evidence, but a weakly-corroborated
candidate with the same network response should still be rejected -- the
softening is specifically about not discarding strong evidence, not about
403 being harmless in general."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app import llm, search
from backend.app.nodes.verify import verify_node


def _state(company):
    return {
        "confirmed_scope": {"layers": ["L"], "layer_definitions": {"L": "def"}},
        "layer_research": {"L": [company]},
    }


def _company(status):
    return {
        "name": "Fervo Energy",
        "url": "https://fervoenergy.com",
        "sources": [{"url": "https://techcrunch.com/x", "title": "x"}],
        "corroboration": {"status": status, "independent_hosts": ["techcrunch.com", "cnbc.com"], "score": 2.0, "detail": "2 independent sources"},
        "one_liner": "",
        "verified": False,
        "category_fit": False,
        "rejection_reason": None,
        "_miscategorized": False,
    }


def test_403_on_a_corroborated_company_downgrades_not_rejects(monkeypatch):
    monkeypatch.setattr(search, "resolve_url", lambda url, **kw: {"resolves": False, "final_url": url, "status": 403})
    monkeypatch.setattr(llm, "company_one_liner", lambda *a, **kw: "a real one-liner")
    monkeypatch.setattr(llm, "category_fit", lambda *a, **kw: (True, "fits"))

    out = verify_node(_state(_company("corroborated")))
    c = out["layer_research"]["L"][0]
    assert c.get("rejection_reason") is None
    assert c["corroboration"]["status"] == "under_corroborated"
    assert "blocked automated verification" in c["corroboration"]["detail"]
    assert c["verified"] is True  # existence softened, category-fit still ran and passed


def test_403_on_a_weakly_corroborated_company_still_rejects(monkeypatch):
    monkeypatch.setattr(search, "resolve_url", lambda url, **kw: {"resolves": False, "final_url": url, "status": 403})

    out = verify_node(_state(_company("under_corroborated")))
    c = out["layer_research"]["L"][0]
    assert c.get("rejection_reason", "").startswith("failed_existence")
    assert c["verified"] is False


def test_hard_failure_status_still_rejects_even_if_corroborated(monkeypatch):
    # status 0 (connection error / DNS failure) is not the ambiguous
    # bot-block signal -- it stays a hard rejection regardless of corroboration.
    monkeypatch.setattr(search, "resolve_url", lambda url, **kw: {"resolves": False, "final_url": url, "status": 0})

    out = verify_node(_state(_company("corroborated")))
    c = out["layer_research"]["L"][0]
    assert c.get("rejection_reason", "").startswith("failed_existence")
