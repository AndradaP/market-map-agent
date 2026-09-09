"""Independent-source-count corroboration: >=2 non-junk domains mentioning a
company is enough, regardless of tier -- see assess_sources()'s docstring for
why gating on count rather than a curated "credible outlets" allowlist is the
deliberate design (a short junk list generalizes across fields; an infinite
"good outlets" list per vertical does not)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.sources import assess_sources


def s(*urls):
    return [{"url": u, "title": u} for u in urls]


def test_two_unclassified_domains_still_corroborate():
    # The whole point: neither host is on any curated list, but two genuinely
    # independent real domains mentioning the company is still real signal.
    r = assess_sources(s("https://some-niche-newsletter.example/x", "https://a-vc-portfolio.example/y"))
    assert r["status"] == "corroborated"
    assert r["score"] == 0.0  # no tier1-3 hit -- score is display-only now
    assert r["tiers"] == []


def test_two_tier3_sources_corroborate():
    r = assess_sources(s("https://techcrunch.com/a", "https://axios.com/b"))
    assert r["status"] == "corroborated"
    assert r["score"] == 2.0
    assert r["tiers"] == ["tier3"]


def test_tier1_plus_tier2_corroborates():
    r = assess_sources(s("https://nist.gov/x", "https://www.bloomberg.com/y"))
    assert r["status"] == "corroborated"
    assert r["score"] == 3.5
    assert r["tiers"] == ["tier1", "tier2"]


def test_single_source_of_any_kind_is_under_corroborated_not_corroborated():
    r = assess_sources(s("https://nist.gov/only"))
    assert r["status"] == "under_corroborated"  # one strong source still isn't two
    r2 = assess_sources(s("https://some-random-blog.example/only"))
    assert r2["status"] == "under_corroborated"  # same rule, unclassified host


def test_existence_only_and_aggregators_do_not_count():
    r = assess_sources(s("https://prnewswire.com/pr", "https://grandviewresearch.com/report"))
    assert r["score"] == 0.0
    assert r["status"] == "uncorroborated"


def test_company_own_domain_never_counts_even_as_the_second_source():
    r = assess_sources(
        s("https://acme.com/about", "https://techcrunch.com/acme"),
        company_host="acme.com",
    )
    assert r["status"] == "under_corroborated"  # only the techcrunch hit counts
    assert r["score"] == 1.0


def test_syndicated_duplicate_titles_count_as_one_source():
    dup = [
        {"url": "https://techcrunch.com/a", "title": "Acme raises 20M Series A led by Foo"},
        {"url": "https://venturebeat.com/b", "title": "Acme raises 20M Series A led by Foo"},
        {"url": "https://www.bloomberg.com/c", "title": "A completely different analysis piece"},
    ]
    r = assess_sources(dup)
    # tc + vb are the same wire story -> one of them drops; bloomberg stays independent
    assert r["status"] == "corroborated"  # 2 genuinely independent stories
    assert r["score"] == 2.5  # 1.0 (one tier3) + 1.5 (bloomberg tier2)
    assert set(r["tiers"]) == {"tier2", "tier3"}


def test_syndicated_duplicates_of_an_unclassified_host_still_collapse():
    # Independence is about the STORY, not the tier -- syndication dedup must
    # still fire even when neither host is on any curated list.
    dup = [
        {"url": "https://blog-a.example/x", "title": "Startup X launches new product"},
        {"url": "https://blog-b.example/y", "title": "Startup X launches new product"},
    ]
    r = assess_sources(dup)
    assert r["status"] == "under_corroborated"  # one real story, not two


def test_recon_supplied_outlets_are_honoured_as_a_display_tier_not_a_gate():
    r = assess_sources(
        s("https://latent.space/p", "https://swyx.io/q"),
        extra_by_tier={"tier3": ["latent.space", "swyx.io"]},
    )
    assert r["status"] == "corroborated"  # 2 independent sources either way
    assert r["score"] == 2.0
    assert r["tiers"] == ["tier3"]


def test_recon_cannot_promote_a_code_host_into_counting_at_all():
    # A real-run bug: recon named github.com tier3 for a dev-tools topic
    # (topically plausible), which would otherwise let a mere repo existing
    # "corroborate" any company that has one. Code/package hosts must never
    # count, regardless of what recon says or how the gate is defined.
    r = assess_sources(
        s("https://github.com/acme/acme", "https://gitlab.com/acme/acme"),
        extra_by_tier={"tier3": ["github.com", "gitlab.com"]},
    )
    assert r["status"] == "uncorroborated"
    assert r["score"] == 0.0
