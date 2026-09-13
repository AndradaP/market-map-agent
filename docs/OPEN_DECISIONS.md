# Open decisions — flagged, not solved silently

The brief lists two explicitly. I hit three more while scaffolding. For each:
what the question is, what I did in the skeleton, and what I think we should do.
None of these are locked in code in a way that's hard to change.

**Status after the a–g iteration pass (see README "Iteration log"):**

- **#2 (empty Exa results)** — resolved. One broadened-query retry now runs before
  a layer is marked `no_results` (edit d); all-empty still ships with a warning.
- **#3 (model split)** — confirmed as-is: `claude-opus-5` judgment / `claude-sonnet-5`
  mechanical.
- **#4 (direct-edit contract)** — resolved. Definitions are editable in the UI,
  required for any added layer; whole-scope payload, no diff. `normalize` flag adds
  an optional one-pass tidy.
- **#1 (clarifying-question wording)** — resolved, see the update below the original
  write-up. The rescope-note clarification copy (edit f) is a separate, still-open
  heuristic that wants a review pass before it's load-bearing.
- **#5 (run-log cost/tokens)** — still open, unchanged below.

---

## 1. Wording & structure of Propose's clarifying questions  *(from the brief)*

**Question.** How should the `open_questions` the model raises be phrased and
shaped so they're actually useful in the confirm UI?

**Skeleton state.** `open_questions` is `list[str]` (matches the draft schema).
The stub writes 2 standalone questions. The prompt in `llm.draft_proposal` tells
the model: "≤3, each a direct standalone question."

**My take.**
- Keep the hard cap at **3**. More than that and the confirm screen stops being
  scannable; the user starts skipping them, which is worse than not asking.
- Each question must be **answerable in the direct-edit UI without a rescope** —
  i.e. it maps to a field the user can just change (a layer name, in/out of
  scope, zoom level). A question the user can't act on without sending it back to
  the model is a rescope prompt in disguise and should be phrased as one.
- Prefer **binary or short-choice** framing: "Should X be its own layer, or
  folded into Y?" beats "How should we handle X?"
- I'd upgrade the type from `str` to
  `{question: str, affects: "layers"|"scope"|"zoom", options?: [str]}` so the UI
  can render them consistently and pre-fill the affected control. Small change,
  but it's a UX decision, so I left it as `str` for you to call.
- **Recommendation:** adopt the structured type; keep the cap at 3; add a prompt
  rule that every question names the field it affects.

**Resolved.** Adopted exactly this, prompted by a live finding, not just the
recommendation above going stale: testing the confirm screen with a real
person, they hit a plain-string question referencing domain jargon ("should
Guardrails be its own layer?") and said they'd need to look the term up to
answer it. `open_questions` is now `list[{question, affects, options}]` —
`affects` names the layer (or "scope"/"zoom_level") it concerns, `options`
gives 2-4 concrete choices. The frontend renders each option as a button;
picking one drafts the rescope note automatically, so answering never
requires already knowing the terminology. `llm._normalize_open_questions`
defensively handles a model response that doesn't fully comply (legacy
plain strings, too many questions/options) rather than trusting it blindly.
Cap stayed at 3, per the original recommendation.

---

## 2. Exa returns nothing usable for a layer  *(from the brief)*

**Question.** What happens to a layer when per-layer research comes back empty or
useless — and it must surface honestly, not silently drop the layer.

**Skeleton state.** Implemented, because "don't silently drop" is unambiguous:
- Layer stays in `final_output.layers` with an empty `companies` list and a
  `status`:
  - `no_results` — search returned nothing usable
  - `no_verified_companies` — candidates found, all failed verification
  - `ok` — ≥1 verified company
- Each non-`ok` layer adds a line to `final_output.warnings`.
- If **every** layer is non-`ok`, an extra warning says the scope is probably off
  and suggests a rescope.

**My take — the parts that are still judgment calls:**
- **Retry before giving up?** Right now Execute does one search per layer. I'd add
  **one** reformulated retry (broaden the query, drop the zoom-level qualifier)
  before marking `no_results` — cheap, and thin layers are often a query-phrasing
  problem. More than one retry isn't worth the latency.
- **All-empty → hard stop or ship?** I ship the map with the warning rather than
  erroring. A map that's honest about being empty is still information ("nobody
  has mapped this / this scope doesn't correspond to a real market"). But if you'd
  rather the agent refuse to finish and bounce back to confirm, that's a
  one-line change in `synthesize` + a new route. **I lean ship-with-warning.**
- **Partial-empty is fine as-is** — don't special-case it.

---

## 3. Judgment vs mechanical model split  *(I hit this)*

**Question.** The brief says "start on Claude for both, downgrade mechanical
later once usage shows it's a problem." Which exact models now?

**Skeleton state.** `config.py` splits them:
`anthropic_model_judgment = claude-opus-5` (Propose, Synthesize),
`anthropic_model_mechanical = claude-sonnet-5` (recon queries, one-liners,
category-fit). Both configurable; nothing downgraded to a non-Claude provider.

**My take.** This matches the brief's intent — spend on the steps where errors
compound, stay cheap-ish on the high-volume mechanical ones — while keeping
everything on Claude so there's one provider to reason about for the demo. Revisit
only when LangSmith shows mechanical calls dominating cost or latency. **I think
this is right; flagging only because I picked the specific model IDs.**

---

## 4. Direct-edit payload contract between frontend and backend  *(I hit this)*

**Question.** A "direct edit" is uncapped and model-free — the user edits fields
themselves. What exactly does the frontend send back?

**Skeleton state.** `user_edit.edited_scope` carries a full `ConfirmedScope`
(layers, layer_definitions, in_scope, excluded_adjacent, zoom_level). The backend
takes it as-is when `type == "direct_edit"`; if it's missing it falls back to the
last proposal. The React form sends the whole scope on every direct edit.

**My take.** Sending the whole scope (not a diff) is simpler and safe — there's
no merge to get wrong. The open bit: **do we let the user edit
`layer_definitions`?** They're load-bearing for Verify's category-fit check. Right
now the form shows them read-only. I think a renamed or newly-added layer should
prompt the user for its one-line definition (or we generate one and let them
tweak), otherwise category-fit checks a layer against a stale definition.
**Recommendation:** make definitions editable, and require one for any layer the
user adds.

---

## 5. What "cost / tokens / latency" in the run log are populated from  *(I hit this)*

**Question.** The log row spec includes cost, token count, latency. Where do those
numbers come from?

**Skeleton state.** Latency we can compute locally. Cost + tokens are left `null`
in stub mode and marked as "backfill from LangSmith when tracing is on" — the run
log writes immediately at end-of-run, but LangSmith trace aggregates settle a
moment later.

**My take.** Two options: (a) a small post-run job that queries the LangSmith run
by `run_id` and updates the row, or (b) accumulate token counts from the Anthropic
responses ourselves as we go and compute cost from a price table. (b) is more code
but doesn't depend on LangSmith being on. **I lean (a)** — it's the whole reason
LangSmith is in the stack — with the row written first and patched within a few
seconds. Needs your call on whether that async patch is acceptable or the row must
be complete on first write.
