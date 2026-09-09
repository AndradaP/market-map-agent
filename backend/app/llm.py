"""Claude calls (Anthropic API). Every public function has a deterministic stub
fallback so the graph runs offline. Real calls are traced via @traceable and
retried with tenacity.

Model split (see brief tech-stack table):
  - judgment   -> Propose, Synthesize  (settings.anthropic_model_judgment)
  - mechanical -> recon queries, one-liners, category-fit
                  (settings.anthropic_model_mechanical)
"""
from __future__ import annotations

import json
from typing import List, Optional, Tuple

from langsmith import traceable
from tenacity import retry, stop_after_attempt, wait_exponential

from . import stubs
from .config import Settings, get_settings

_client_cache = {}


def _client(settings: Settings):
    if "c" not in _client_cache:
        from anthropic import Anthropic

        kwargs = {"api_key": settings.anthropic_api_key}
        # Pin the real API unless explicitly overridden, so an ambient
        # ANTHROPIC_BASE_URL (e.g. a proxy) can't misroute the standalone agent.
        kwargs["base_url"] = settings.anthropic_base_url or "https://api.anthropic.com"
        if settings.anthropic_workspace_id:
            kwargs["default_headers"] = {
                "anthropic-workspace-id": settings.anthropic_workspace_id
            }
        _client_cache["c"] = Anthropic(**kwargs)
    return _client_cache["c"]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=20), reraise=True)
def _json_call(settings: Settings, *, model: str, system: str, user: str) -> dict:
    """One Claude call that must return a single JSON object."""
    msg = _client(settings).messages.create(
        model=model,
        max_tokens=2000,
        system=system + "\n\nRespond with a single valid JSON object and nothing else.",
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip()
    return json.loads(text)


# --------------------------------------------------------------------------- #
# Recon: query generation
# --------------------------------------------------------------------------- #
@traceable(run_type="llm", name="claude.recon_queries")
def recon_queries(topic: str, *, settings: Optional[Settings] = None) -> List[str]:
    settings = settings or get_settings()
    if settings.stubs_enabled:
        return stubs.recon_queries(topic)
    out = _json_call(
        settings,
        model=settings.anthropic_model_mechanical,
        system="You generate broad web-search queries to survey a topic before any scoping decision.",
        user=(
            f"Topic: {topic!r}. Produce 5-7 diverse search queries that would surface how this "
            'space is structured and who operates in it. JSON: {"queries": [str, ...]}.'
        ),
    )
    return list(out.get("queries", []))[:7]


@traceable(run_type="llm", name="claude.credible_outlets")
def credible_outlets(
    topic: str, recon_results: list, *, settings: Optional[Settings] = None
) -> dict:
    """Recon identifies which named outlets are tier 1/2/3 *for this topic*.
    Merged on top of the static host lists in sources.py (a backstop only)."""
    settings = settings or get_settings()
    if settings.stubs_enabled:
        return stubs.credible_outlets(topic)
    snippets = "\n".join(
        f"- {r.get('title','')} ({r.get('url','')})" for r in recon_results[:30]
    )
    out = _json_call(
        settings,
        model=settings.anthropic_model_mechanical,
        system=(
            "You classify news/research outlets by credibility tier for a specific topic. "
            "Tier 1: primary & authoritative — regulators, standards bodies, peer-reviewed "
            "journals. Tier 2: established press & major research houses. Tier 3: credible "
            "trade press & informed newsletters/VC blogs. Only list outlets that actually "
            "appear or are clearly relevant; use bare domains."
        ),
        user=(
            f"Topic: {topic!r}\n\nOutlets seen in recon:\n{snippets}\n\n"
            'JSON: {"tier1": [domain, ...], "tier2": [...], "tier3": [...]}.'
        ),
    )
    return {k: list(out.get(k, [])) for k in ("tier1", "tier2", "tier3")}


# --------------------------------------------------------------------------- #
# Propose: draft the value-chain skeleton  (judgment model)
# --------------------------------------------------------------------------- #
@traceable(run_type="llm", name="claude.draft_proposal")
def draft_proposal(
    *,
    topic: str,
    recon_results: list,
    rescope_notes: str = "",
    attempt: int = 1,
    settings: Optional[Settings] = None,
) -> dict:
    settings = settings or get_settings()
    if settings.stubs_enabled:
        return stubs.proposal(topic, attempt=attempt, rescope_notes=rescope_notes)

    snippets = "\n".join(
        f"- {r.get('title','')}: {r.get('text','')[:280]} ({r.get('url','')})"
        for r in recon_results[:25]
    )
    rescope_block = (
        f"\n\nThis is rescope attempt {attempt}. The user said the previous proposal was off:\n"
        f'"{rescope_notes}"\nAddress that specifically.'
        if rescope_notes
        else ""
    )
    out = _json_call(
        settings,
        model=settings.anthropic_model_judgment,
        system=(
            "You are scoping a value chain + market map. Propose a BOUNDED structure, not an "
            "exhaustive one. If recon is thin or contradictory, say so honestly in `notes` rather "
            "than forcing a confident structure."
        ),
        user=(
            f"Topic: {topic!r}\n\nRecon snippets:\n{snippets}{rescope_block}\n\n"
            "Return JSON with keys: layers (list[str], 3-7), layer_definitions "
            "(object mapping each layer -> one sentence), in_scope (list[str]), "
            "excluded_adjacent (list[str]), zoom_level ('component'|'company'|'category'), "
            "open_questions (list[str], <=3, each a direct standalone question), notes (str)."
        ),
    )
    # The model doesn't always include every requested key (seen live: a real
    # response once omitted zoom_level entirely) -- default the full Proposal
    # shape rather than let a downstream consumer KeyError on a skipped field.
    out.setdefault("layers", [])
    out.setdefault("layer_definitions", {})
    out.setdefault("in_scope", [])
    out.setdefault("excluded_adjacent", [])
    out.setdefault("zoom_level", "company")
    out.setdefault("open_questions", [])
    out.setdefault("notes", "")
    return out


# --------------------------------------------------------------------------- #
# Execute: company extraction  (mechanical model)
# --------------------------------------------------------------------------- #
@traceable(run_type="llm", name="claude.extract_companies")
def extract_companies(
    hits: List[dict],
    *,
    topic: str,
    layer: str,
    definition: str,
    cap: int,
    settings: Optional[Settings] = None,
) -> List[dict]:
    """Pull real, named companies + primary URLs out of a batch of search hits.

    One call over ALL hits together, not one per hit: a single hit (a "top 10"
    roundup) often names several companies, and the same company often recurs
    across hits — the model dedupes both directions in one pass instead of us
    fuzzy-matching names afterwards. No stub fallback: find_company_sources
    short-circuits to the stub fixtures before this is ever called.
    """
    settings = settings or get_settings()
    snippets = "\n".join(
        f"- {h.get('title','')}: {h.get('text','')[:500]} ({h.get('url','')})" for h in hits
    )
    out = _json_call(
        settings,
        model=settings.anthropic_model_mechanical,
        system=(
            "You extract real, named companies/products/projects from web search "
            "results, for one layer of a value-chain market map. Only extract "
            "entities actually named in the text — never invent one. Merge repeat "
            "mentions of the same company into a single entry. Skip generic "
            "mentions with no identifiable name, and skip the outlet/publication "
            "itself (e.g. don't extract 'TechCrunch' from a TechCrunch article)."
        ),
        user=(
            f"Topic: {topic!r}\nLayer: {layer!r}\nLayer definition: {definition!r}\n\n"
            f"Search results:\n{snippets}\n\n"
            f"Extract up to {cap} distinct companies that plausibly belong in this "
            "layer. For each, give its primary/official URL (the company's own "
            "site, not the article about it). Use the URL from the text if it's "
            "there; for a well-known company you're confident you know the real "
            "domain of even if it isn't in the text, supply it from your own "
            "knowledge. Only use null when you aren't reasonably confident of the "
            "actual domain — never fabricate one for an obscure or ambiguous name.\n"
            'JSON: {"companies": [{"name": str, "url": str|null}, ...]}.'
        ),
    )
    seen = set()
    result: List[dict] = []
    for c in out.get("companies", []):
        name = (c.get("name") or "").strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        result.append({"name": name, "url": (c.get("url") or "").strip()})
        if len(result) >= cap:
            break
    return result


# --------------------------------------------------------------------------- #
# Verify + Synthesize helpers  (mechanical / judgment)
# --------------------------------------------------------------------------- #
@traceable(run_type="llm", name="claude.company_one_liner")
def company_one_liner(
    name: str,
    url: str,
    evidence: List[str],
    *,
    layer: str = "",
    layer_definition: str = "",
    settings: Optional[Settings] = None,
) -> str:
    settings = settings or get_settings()
    if settings.stubs_enabled:
        return stubs.one_liner(name, url, layer, layer_definition)
    out = _json_call(
        settings,
        model=settings.anthropic_model_mechanical,
        system=(
            "Write ONE sentence, 12-25 words (never more than 30), describing what this "
            "company is or does — what a reviewer of a market map needs to see its fit.\n"
            "Structure: [what it is/does] -> [for whom or on what] -> [the mechanism that "
            "sets it apart, ONLY if the evidence states it].\n"
            f"Lead with the function that matches this layer: {layer or '(unspecified)'} "
            f"— defined as: {layer_definition or '(no definition given)'}.\n"
            "Rules: name the concrete product category, not a marketing abstraction. Ground "
            "every claim in the evidence; if the evidence doesn't say HOW it works, don't "
            "invent a mechanism. Banned: 'leading', 'innovative', 'best-in-class', "
            "'cutting-edge', 'leverages', 'empowers', 'enables', and the company's own "
            "tagline verbatim. A comparative anchor ('a managed alternative to running X') "
            "is fine when it is the clearest framing."
        ),
        user=(
            f"Company: {name} ({url})\nLayer: {layer}\nLayer definition: {layer_definition}\n"
            "Evidence (retrieved text):\n"
            + "\n".join(f"- {e}" for e in evidence)
            + '\n\nJSON: {"one_liner": str}.'
        ),
    )
    return out.get("one_liner", "").strip()


@traceable(run_type="llm", name="claude.normalize_scope")
def normalize_scope(scope: dict, *, settings: Optional[Settings] = None) -> dict:
    """One cheap pass to tidy user-added layer names/order + fill missing definitions.
    MUST NOT add/remove layers or change in_scope / excluded_adjacent / zoom_level."""
    settings = settings or get_settings()
    if settings.stubs_enabled:
        return stubs.normalize_scope(scope)
    out = _json_call(
        settings,
        model=settings.anthropic_model_mechanical,
        system=(
            "Tidy a value-chain scope the user edited by hand: make layer names parallel in "
            "phrasing, put them in a sensible upstream->downstream order, and write a "
            "one-sentence definition for any layer missing one. Do NOT add or remove layers, "
            "and do NOT change in_scope, excluded_adjacent or zoom_level."
        ),
        user=(
            f"Scope:\n{json.dumps(scope, indent=2)}\n\n"
            "Return the same JSON shape (layers, layer_definitions, in_scope, "
            "excluded_adjacent, zoom_level) with only naming/order/definitions adjusted."
        ),
    )
    out.setdefault("in_scope", scope.get("in_scope", []))
    out.setdefault("excluded_adjacent", scope.get("excluded_adjacent", []))
    out.setdefault("zoom_level", scope.get("zoom_level", "company"))
    return out


@traceable(run_type="llm", name="claude.rescope_clarifying_question")
def rescope_clarifying_question(
    notes: str, proposal: dict, *, settings: Optional[Settings] = None
) -> str:
    """One pointed question when a rescope request is too vague to act on."""
    settings = settings or get_settings()
    if settings.stubs_enabled:
        return stubs.rescope_clarifying_question(notes, proposal)
    out = _json_call(
        settings,
        model=settings.anthropic_model_mechanical,
        system=(
            "A user asked to rescope a value-chain proposal but their note is too vague to "
            "act on. Ask exactly ONE concrete question whose answer would let us re-scope "
            "well. Reference the actual proposed layers."
        ),
        user=(
            f"Proposed layers: {proposal.get('layers', [])}\n"
            f"User's note: {notes!r}\n\nJSON: {{\"question\": str}}."
        ),
    )
    return out.get("question", stubs.rescope_clarifying_question(notes, proposal)).strip()


@traceable(run_type="llm", name="claude.category_fit")
def category_fit(
    one_liner_text: str,
    layer: str,
    definition: str,
    *,
    miscategorized_hint: bool = False,
    settings: Optional[Settings] = None,
) -> Tuple[bool, str]:
    settings = settings or get_settings()
    if settings.stubs_enabled:
        return stubs.category_fit(one_liner_text, layer, definition, miscategorized=miscategorized_hint)
    out = _json_call(
        settings,
        model=settings.anthropic_model_mechanical,
        system="Decide whether a company belongs in a value-chain layer, given the layer's definition and a grounded one-liner.",
        user=(
            f"Layer: {layer}\nLayer definition: {definition}\nCompany one-liner: {one_liner_text}\n\n"
            'JSON: {"fits": bool, "reason": str}.'
        ),
    )
    return bool(out.get("fits", False)), out.get("reason", "")


@traceable(run_type="llm", name="claude.layer_explanation")
def layer_explanation(
    layer: str,
    definition: str,
    adjacent: List[str],
    companies: list,
    *,
    settings: Optional[Settings] = None,
) -> str:
    settings = settings or get_settings()
    if settings.stubs_enabled:
        return stubs.layer_explanation(layer, definition, adjacent, companies)
    names = ", ".join(c.get("name", "") for c in companies) or "none yet"
    out = _json_call(
        settings,
        model=settings.anthropic_model_judgment,
        system="Write a one-paragraph explanation of a value-chain layer and how it connects to adjacent layers.",
        user=(
            f"Layer: {layer}\nDefinition: {definition}\nExcluded-adjacent: {', '.join(adjacent) or 'none'}\n"
            f"Verified companies: {names}\n\nJSON: {{\"explanation\": str}}."
        ),
    )
    return out.get("explanation", "").strip()
