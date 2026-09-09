"""Source-credibility tiering + the two-source corroboration rule.

This is the brief's typology turned into code. It is deliberately a *definition*
plus heuristics, not a per-vertical name list: Recon is expected to hand in the
vertical-specific tier-1..3 outlets it discovers (``extra_by_tier``), and those
are merged on top of the generic defaults below.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence

from .utils import host_of

GOV_SUFFIXES = (".gov", ".gov.uk", ".mil", ".europa.eu", ".int")
EDU_SUFFIXES = (".edu", ".ac.uk", ".edu.au")

# Tier 1 — primary & authoritative (standards bodies, regulators, journals).
TIER1_HOSTS = {
    "nist.gov", "energy.gov", "epa.gov", "faa.gov", "nasa.gov", "who.int",
    "nature.com", "science.org", "sciencedirect.com", "ieee.org", "acm.org",
    "awwa.org", "spe.org", "astm.org", "iso.org", "ietf.org",
}
# Tier 2 — established press & research houses.
TIER2_HOSTS = {
    "wsj.com", "bloomberg.com", "ft.com", "reuters.com", "economist.com",
    "nytimes.com", "hbr.org", "mckinsey.com", "bcg.com", "deloitte.com",
    "bain.com", "pwc.com", "gartner.com", "forrester.com", "pitchbook.com",
}
# Tier 3 — trade press & informed newsletters (startup-adjacent lives HERE).
TIER3_HOSTS = {
    "techcrunch.com", "theinformation.com", "axios.com", "crunchbase.com",
    "ycombinator.com", "tldr.tech", "stratechery.com", "protocol.com",
    "waterworld.com", "hartenergy.com", "aviationweek.com", "evtol.com",
    "a16z.com", "sequoiacap.com", "greylock.com", "nfx.com", "bvp.com",
    "github.blog", "thenewstack.io", "infoq.com", "venturebeat.com",
}
# Existence-only — confirms what a company claims, never counts toward the two.
# Includes code/package hosts: a repo or package listing existing is not
# independent editorial coverage, however relevant the host is to the topic
# (see classify(): this list overrides even recon-supplied extra_by_tier).
EXISTENCE_ONLY_HOSTS = {
    "prnewswire.com", "businesswire.com", "globenewswire.com", "einnews.com",
    "prweb.com", "medium.com", "substack.com", "linkedin.com",
    "github.com", "gitlab.com", "bitbucket.org", "npmjs.com",
    "registry.npmjs.org", "pypi.org", "marketplace.visualstudio.com",
}
# Explicitly excluded — scraped/republished "free market research" aggregators.
EXCLUDED_HOSTS = {
    "marketsandmarkets.com", "grandviewresearch.com", "mordorintelligence.com",
    "researchandmarkets.com", "alliedmarketresearch.com", "fortunebusinessinsights.com",
    "marketresearchfuture.com", "imarcgroup.com", "precedenceresearch.com",
    "verifiedmarketresearch.com", "futuremarketinsights.com",
}

Tier = str  # "tier1" | "tier2" | "tier3" | "existence_only" | "excluded" | "unknown"


def classify(url: str, *, company_host: Optional[str] = None,
             extra_by_tier: Optional[Dict[str, Sequence[str]]] = None) -> Tier:
    h = host_of(url)
    if not h:
        return "unknown"
    if company_host and (h == company_host or h.endswith("." + company_host)):
        return "existence_only"

    # Hardcoded non-counting hosts win even over recon-supplied extra_by_tier:
    # Recon names outlets that are *topically* relevant, but a code host or a
    # PR wire isn't independent editorial coverage no matter how on-topic it
    # is — e.g. recon calling github.com "tier3" for a dev-tools query would
    # otherwise let a mere repo existing corroborate the company.
    if h in EXCLUDED_HOSTS:
        return "excluded"
    if h in EXISTENCE_ONLY_HOSTS:
        return "existence_only"

    extra_by_tier = extra_by_tier or {}
    for tier in ("tier1", "tier2", "tier3"):
        if h in {host_of(x) for x in extra_by_tier.get(tier, [])}:
            return tier

    if h in TIER1_HOSTS or h.endswith(GOV_SUFFIXES) or h.endswith(EDU_SUFFIXES):
        return "tier1"
    if h in TIER2_HOSTS:
        return "tier2"
    if h in TIER3_HOSTS:
        return "tier3"
    return "unknown"


CORROBORATING = {"tier1", "tier2", "tier3"}
TIER_WEIGHTS = {"tier1": 2.0, "tier2": 1.5, "tier3": 1.0}


def _title_tokens(t: str) -> set:
    return set(re.findall(r"[a-z0-9]{3,}", (t or "").lower()))


def _same_story(a: str, b: str, thr: float = 0.85) -> bool:
    """Cheap syndication check: near-identical headlines => one story, not two sources."""
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= thr


def assess_sources(
    source_meta: Sequence[dict],
    *,
    company_host: Optional[str] = None,
    extra_by_tier: Optional[Dict[str, Sequence[str]]] = None,
    threshold: float = 3.0,
) -> dict:
    """Tier-weighted corroboration over a company's sources.

    ``source_meta``: ``[{"url": str, "title": str}, ...]``.

    Independence: one contribution per distinct host (best tier wins), and
    near-duplicate headlines across hosts are treated as a single syndicated
    story (the lower tier is dropped).

    Returns ``{status, score, tiers, independent_hosts, detail}`` where status is
    ``corroborated`` (score >= threshold and >= 2 independent sources),
    ``under_corroborated`` (>= 1 tier1-3 source but bar not met), or
    ``uncorroborated`` (no tier1-3 source at all).
    """
    # best tier per host
    by_host: Dict[str, dict] = {}
    for s in source_meta:
        url = s.get("url", "") if isinstance(s, dict) else str(s)
        title = s.get("title", "") if isinstance(s, dict) else ""
        tier = classify(url, company_host=company_host, extra_by_tier=extra_by_tier)
        if tier not in CORROBORATING:
            continue
        h = host_of(url)
        if not h:
            continue
        cur = by_host.get(h)
        if cur is None or TIER_WEIGHTS[tier] > TIER_WEIGHTS[cur["tier"]]:
            by_host[h] = {"tier": tier, "title": title, "url": url}

    # drop syndicated duplicates (keep the higher tier)
    kept: List[dict] = []
    for entry in sorted(by_host.values(), key=lambda e: -TIER_WEIGHTS[e["tier"]]):
        if any(_same_story(entry["title"], k["title"]) for k in kept):
            continue
        kept.append(entry)

    score = round(sum(TIER_WEIGHTS[e["tier"]] for e in kept), 2)
    tiers = sorted({e["tier"] for e in kept})
    hosts = [host_of(e["url"]) for e in kept]

    if score >= threshold and len(kept) >= 2:
        status = "corroborated"
    elif len(kept) >= 1:
        status = "under_corroborated"
    else:
        status = "uncorroborated"

    if status == "corroborated":
        detail = f"score {score} across {', '.join(tiers)} ({', '.join(hosts)})"
    elif status == "under_corroborated":
        detail = (
            f"score {score} (want >= {threshold}); {len(kept)} independent tier1-3 "
            f"source(s): {', '.join(hosts)}"
        )
    else:
        detail = "no independent tier1-3 sources (existence-only and aggregators do not count)"

    return {
        "status": status,
        "score": score,
        "tiers": tiers,
        "independent_hosts": hosts,
        "detail": detail,
    }
