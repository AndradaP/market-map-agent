from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

try:  # py3.9 has Literal in typing
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

ZoomLevel = Literal["component", "company", "category"]
EditType = Literal["none", "direct_edit", "rescope_request"]


class OpenQuestion(TypedDict, total=False):
    question: str
    # Short label naming what this concerns -- usually a layer name from
    # `layers`, or "scope"/"zoom_level" when it's not about one specific
    # layer. Purely informational context for the UI, not a dispatch key.
    affects: str
    # 2-4 concrete choices the user can pick without outside research, or
    # [] when the question is genuinely open-ended. Resolves the open design
    # question (see OPEN_DECISIONS.md): a live UX test found a plain-string
    # question referencing domain jargon ("should Guardrails be its own
    # layer?") is unanswerable without looking the term up -- a concrete
    # pick-one choice tied to a real, visible layer isn't.
    options: List[str]


class Proposal(TypedDict, total=False):
    layers: List[str]
    # DEVIATION FROM DRAFT SCHEMA: the draft had `layers: [str]` only. Verify's
    # category-fit check needs "that layer's stated definition from the confirmed
    # scope", so each layer carries a one-line definition here.
    layer_definitions: Dict[str, str]
    in_scope: List[str]
    excluded_adjacent: List[str]
    zoom_level: ZoomLevel
    open_questions: List[OpenQuestion]
    # Propose's honest caveats when recon is thin or contradictory (brief asks
    # for this behaviour explicitly under "Explicitly out of scope for v1").
    notes: str


class ConfirmedScope(TypedDict, total=False):
    layers: List[str]
    layer_definitions: Dict[str, str]
    in_scope: List[str]
    excluded_adjacent: List[str]
    zoom_level: ZoomLevel


class UserEdit(TypedDict, total=False):
    type: EditType
    notes: str
    different_topic: bool  # only true if the user ticks the box; triggers fresh recon
    edited_scope: Optional[ConfirmedScope]  # payload of a direct_edit
    normalize: bool  # direct_edit: run one cheap LLM pass to tidy names/order (not a rescope)


class Corroboration(TypedDict, total=False):
    # corroborated = >=2 independent non-junk sources, regardless of tier;
    # under_corroborated = exactly 1; uncorroborated = 0. See sources.py.
    status: Literal["corroborated", "under_corroborated", "uncorroborated"]
    independent_hosts: List[str]  # the distinct hosts that counted toward status
    score: float          # tier-weighted sum -- display only, doesn't gate status
    tiers: List[str]      # distinct tier1-3 tiers present, e.g. ["tier1"] -- for a "featured in" badge
    detail: str


class Company(TypedDict, total=False):
    name: str
    url: str
    one_liner: str
    sources: List[str]  # corroborating source URLs
    verified: bool       # passed existence + category-fit
    category_fit: bool
    corroboration: Corroboration
    rejection_reason: Optional[str]
    layer: str  # set when surfaced in final_output.rejected / needs_review


class LayerResult(TypedDict, total=False):
    name: str
    explanation: str
    status: Literal["ok", "no_results", "no_verified_companies"]
    companies: List[Company]  # corroborated + verified only
    under_corroborated_count: int
    reformulated: bool  # first search was empty; a broadened query was used
    over_cap: bool      # more candidates than the hard cap; list was truncated


class FinalOutput(TypedDict, total=False):
    topic: str
    zoom_level: ZoomLevel
    layers: List[LayerResult]
    rejected: List[Company]        # failed a hard check — visible, each with a reason
    needs_review: List[Company]    # passed existence+fit but under-corroborated — for the human to rescue
    warnings: List[str]
    generated_at: str


class MarketMapState(TypedDict, total=False):
    topic: str
    run_id: str

    recon_results: List[Dict[str, Any]]
    # Vertical-specific credible outlets Recon identified, by tier. Merged on top
    # of the static host lists in sources.py (which are only a backstop).
    credible_outlets: Dict[str, List[str]]

    proposal: Proposal
    propose_attempts: int
    rescope_count: int  # capped at settings.rescope_cap
    cap_hit: bool
    force_direct_edit: bool
    handoff_message: Optional[str]

    user_edit: UserEdit
    confirmed_scope: ConfirmedScope

    layer_research: Dict[str, List[Company]]  # per-layer candidate lists
    layer_meta: Dict[str, Any]               # per-layer: raw_count, reformulated, over_cap

    final_output: FinalOutput
    metrics: Dict[str, Any]
