from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

try:  # py3.9 has Literal in typing
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

ZoomLevel = Literal["component", "company", "category"]
EditType = Literal["none", "direct_edit", "rescope_request"]


class QuestionOption(TypedDict, total=False):
    # Short choice label, e.g. "include" / "exclude".
    label: str
    # The scope chips this option contributes when it's the selected one.
    # Each question owns its chips: switching options swaps this option's
    # chips in and the previously selected option's chips out, so the
    # answer is visible in the In scope / Excluded lists rather than
    # recorded somewhere the user can't see.
    in_scope: List[str]
    excluded: List[str]


class OpenQuestion(TypedDict, total=False):
    """A scoping call the model wants a human on, shaped as a SETTING rather
    than a question.

    The original design (OPEN_DECISIONS.md #1) required every question be
    answerable in the direct-edit UI without spending a rescope. The first
    implementation drifted: answers drafted a rescope note instead, so the
    only way to answer was to spend an attempt and have the model redraft.
    Worse, two of the three kinds of question it asked (scope boundaries,
    per-layer breadth) reached nothing downstream at all.

    Now `question` is a short label ("Large incumbents"), `options` are the
    settings it can take, and picking one edits the scope directly. Free,
    instant, no model call.
    """

    # SHORT label, not a sentence -- it renders as a settings row.
    question: str
    # 2-4 options, or [] when the question is genuinely open-ended and the
    # answer is free text appended to `guidance`.
    options: List[QuestionOption]
    # Index of the option the proposal already took, so the control opens
    # on the model's own choice instead of an empty state.
    default: Optional[int]


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
    # How many companies to aim for per layer. Was a global constant
    # (`layer_company_hard_cap`), which meant the model could ask "how wide
    # should this layer go?" and the answer changed nothing.
    companies_per_layer: int
    # Free-text steer for anything the controls don't capture ("European
    # players only", "Series A and later"). Reaches the per-layer search
    # query and the category-fit check, so it actually bites.
    guidance: str


class UserEdit(TypedDict, total=False):
    type: EditType
    notes: str
    different_topic: bool  # only true if the user ticks the box; triggers fresh recon
    edited_scope: Optional[ConfirmedScope]  # payload of a direct_edit


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
