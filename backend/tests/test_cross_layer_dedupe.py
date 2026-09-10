"""Synthesize's cross-layer dedup: each layer's research runs in isolation
(execute.py), so the same real company routinely gets extracted independently
by more than one layer -- seen live, ~15% of a run's entries could be the same
handful of companies repeated 2-3x, sometimes with a cosmetic URL difference
(www., trailing slash) that made the SAME company resolve in one layer and
transiently fail existence in another."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.nodes.synthesize import _dedupe_across_layers


def _company(name, url, status="corroborated", hosts=None, score=0.0):
    return {
        "name": name,
        "url": url,
        "verified": True,
        "corroboration": {"status": status, "independent_hosts": hosts or [], "score": score},
    }


def test_same_company_across_two_layers_keeps_only_the_better_one():
    research = {
        "Layer A": [_company("Acme", "https://acme.com", status="corroborated", hosts=["a.com", "b.com"])],
        "Layer B": [_company("Acme Inc", "https://www.acme.com/", status="under_corroborated", hosts=["a.com"])],
    }
    out = _dedupe_across_layers(research)
    assert [c["name"] for cands in out.values() for c in cands] == ["Acme"]
    assert out["Layer B"] == []


def test_cosmetic_url_differences_collapse_to_the_same_host():
    research = {
        "Layer A": [_company("Vulcan", "https://v-er.eu", status="corroborated", hosts=["x", "y"])],
        "Layer B": [_company("Vulcan Energy", "https://v-er.eu/", status="corroborated", hosts=["x", "y"])],
        "Layer C": [_company("Vulcan Energy", "https://www.v-er.eu/", status="uncorroborated")],
    }
    out = _dedupe_across_layers(research)
    total = sum(len(c) for c in out.values())
    assert total == 1


def test_distinct_companies_are_left_alone():
    research = {
        "Layer A": [_company("Acme", "https://acme.com")],
        "Layer B": [_company("Zeta", "https://zeta.com")],
    }
    out = _dedupe_across_layers(research)
    assert sum(len(c) for c in out.values()) == 2


def test_companies_with_no_url_are_never_deduped_away():
    research = {
        "Layer A": [_company("NoUrlCo", "")],
        "Layer B": [_company("NoUrlCo", "")],
    }
    out = _dedupe_across_layers(research)
    assert sum(len(c) for c in out.values()) == 2
