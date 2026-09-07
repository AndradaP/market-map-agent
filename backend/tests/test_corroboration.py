"""Tier-weighted corroboration (edit c) + syndication independence check."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.sources import assess_sources

TH = 3.0


def s(*urls):
    return [{"url": u, "title": u} for u in urls]


def test_two_tier3_is_under_corroborated():
    r = assess_sources(s("https://techcrunch.com/a", "https://axios.com/b"), threshold=TH)
    assert r["score"] == 2.0
    assert r["status"] == "under_corroborated"
    assert r["tiers"] == ["tier3"]


def test_tier1_plus_tier2_clears_bar():
    r = assess_sources(s("https://nist.gov/x", "https://www.bloomberg.com/y"), threshold=TH)
    assert r["score"] == 3.5
    assert r["status"] == "corroborated"
    assert r["tiers"] == ["tier1", "tier2"]


def test_single_strong_source_is_under_not_corroborated():
    r = assess_sources(s("https://nist.gov/only"), threshold=TH)
    assert r["status"] == "under_corroborated"  # score 2.0 but only one independent source


def test_existence_only_and_aggregators_do_not_count():
    r = assess_sources(
        s("https://prnewswire.com/pr", "https://grandviewresearch.com/report"), threshold=TH
    )
    assert r["score"] == 0.0
    assert r["status"] == "uncorroborated"


def test_company_own_domain_is_existence_only():
    r = assess_sources(
        s("https://acme.com/about", "https://techcrunch.com/acme"),
        company_host="acme.com",
        threshold=TH,
    )
    assert r["score"] == 1.0  # only the techcrunch hit counts
    assert r["status"] == "under_corroborated"


def test_syndicated_duplicate_titles_count_once():
    dup = [
        {"url": "https://techcrunch.com/a", "title": "Acme raises 20M Series A led by Foo"},
        {"url": "https://venturebeat.com/b", "title": "Acme raises 20M Series A led by Foo"},
        {"url": "https://www.bloomberg.com/c", "title": "A completely different analysis piece"},
    ]
    r = assess_sources(dup, threshold=TH)
    # tc + vb are the same wire story -> one of them drops; bloomberg stays
    assert r["score"] == 2.5  # 1.0 (one tier3) + 1.5 (bloomberg tier2)
    assert set(r["tiers"]) == {"tier2", "tier3"}


def test_recon_supplied_outlets_are_honoured():
    r = assess_sources(
        s("https://latent.space/p", "https://swyx.io/q"),
        extra_by_tier={"tier3": ["latent.space", "swyx.io"]},
        threshold=TH,
    )
    assert r["status"] == "under_corroborated"
    assert r["score"] == 2.0
