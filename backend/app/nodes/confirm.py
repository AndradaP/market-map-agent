"""Node 3 — Confirm or edit. The human-in-the-loop gate.

A real durable pause via LangGraph ``interrupt()`` / ``Command(resume=...)`` — not
a retry loop. Routing out of this node lives in ``graph.route_after_confirm``.

Rescope cap (brief): capped at ``settings.rescope_cap`` rescope *requests*
(cap + 1 propose attempts total), stated upfront on the first proposal screen.
On hitting the cap the agent flips to direct-edit-only and says why.

Rescope-note quality gate (edit f): if a rescope note is too thin to act on, the
node asks ONE clarifying question via a second ``interrupt()`` — this round does
NOT spend a rescope attempt. Only one free round per submission.
"""
from __future__ import annotations

from langgraph.types import interrupt

from .. import llm
from ..config import get_settings
from ..state import MarketMapState

HANDOFF_TEMPLATE = (
    "We've tried scoping this {n} times and it still isn't landing. Over to you: "
    "edit the structure directly below."
)

_EDIT_KEYWORDS = (
    "scope", "exclude", "includ", "broad", "narrow", "split", "merge", "combine",
    "separate", "layer", "stage", "component", "categor", "granular", "rename",
    "reorder", "sub-cat", "subcateg", "out of scope",
)
_DIRECT_EDIT_VERBS = ("rename", "remove", "drop", "delete", "split", "merge", "reorder", "add")


def note_is_actionable(notes: str, layers, min_chars: int) -> bool:
    """Cheap floor — is this rescope note worth spending an attempt on? No model."""
    n = (notes or "").strip()
    if len(n) < min_chars:
        return False
    low = n.lower()
    if any(str(l).lower() in low for l in (layers or [])):
        return True
    if any(k in low for k in _EDIT_KEYWORDS):
        return True
    return len(n) >= 40


def looks_like_direct_edit(notes: str, layers) -> bool:
    """Note names a layer and a do-it-yourself verb -> suggest a free direct edit."""
    low = (notes or "").lower()
    names_layer = any(str(l).lower() in low for l in (layers or []))
    has_verb = any(v in low for v in _DIRECT_EDIT_VERBS)
    return names_layer and has_verb


def confirm_node(state: MarketMapState) -> dict:
    settings = get_settings()
    cap = settings.rescope_cap
    used = state.get("rescope_count", 0)
    already_capped = state.get("cap_hit", False)
    proposal = state["proposal"]
    layers = proposal.get("layers", [])

    payload = {
        "kind": "proposal_review",
        "run_id": state.get("run_id"),
        "topic": state.get("topic"),
        "proposal": proposal,
        "attempt": state.get("propose_attempts", 1),
        "rescope_cap": cap,
        "rescopes_used": used,
        "rescopes_remaining": max(0, cap - used),
        "direct_edit_only": already_capped,
        "handoff_message": state.get("handoff_message"),
        "min_note_chars": settings.rescope_min_note_chars,
    }

    # -- suspend here; resumes with Command(resume=<UserEdit dict>) --
    reply = interrupt(payload) or {}
    etype = reply.get("type", "none")

    # --- rescope cap enforcement ---
    if etype == "rescope_request" and used >= cap:
        return {
            "user_edit": reply,
            "cap_hit": True,
            "force_direct_edit": True,
            "handoff_message": HANDOFF_TEMPLATE.format(n=used + 1),
        }

    if etype == "rescope_request":
        notes = reply.get("notes", "")
        # One free clarification round if the note is too thin (does NOT spend an attempt).
        if not note_is_actionable(notes, layers, settings.rescope_min_note_chars):
            answer = interrupt(
                {
                    "kind": "rescope_clarification",
                    "run_id": state.get("run_id"),
                    "original_notes": notes,
                    "question": llm.rescope_clarifying_question(notes, proposal),
                    "proposal": proposal,
                }
            ) or {}
            extra = (answer.get("notes") or answer.get("clarification") or "").strip()
            notes = " — ".join(x for x in (notes.strip(), extra) if x)
            reply = {**reply, "notes": notes}

        # Granted: bump the counter; graph routes back to Recon or Propose.
        return {"user_edit": reply, "rescope_count": used + 1}

    # --- confirm as-is ("none") or direct_edit: lock the scope and move on ---
    if etype == "direct_edit" and reply.get("edited_scope"):
        scope = reply["edited_scope"]
        if reply.get("normalize"):
            scope = llm.normalize_scope(scope)
    else:
        scope = {
            "layers": proposal.get("layers", []),
            "layer_definitions": proposal.get("layer_definitions", {}),
            "in_scope": proposal.get("in_scope", []),
            "excluded_adjacent": proposal.get("excluded_adjacent", []),
            "zoom_level": proposal.get("zoom_level", "company"),
        }

    return {"user_edit": reply, "confirmed_scope": scope}
