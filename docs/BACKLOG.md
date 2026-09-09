# Backlog — internal

Not for `main`. Tracks what's done and what's next. Pairs with
[`OPEN_DECISIONS.md`](OPEN_DECISIONS.md).

---

## Done

### M0 — skeleton
- [x] Repo scaffold; Python 3.9 venv; deps pinned (`requirements*.txt`).
- [x] State schema as `TypedDict`s (`backend/app/state.py`).
- [x] Six-node graph wired with the rescope back-edge + router (`graph.py`, `nodes/`).
- [x] Confirm gate: real `interrupt()` / `Command(resume=…)`, not a retry loop.
- [x] Rescope cap (default 2) enforced; stated up front; direct-edit takeover on the cap.
- [x] LangSmith tracing wired (`tracing.py`); `@traceable` on the llm/search calls.
- [x] Checkpointer: PostgresSaver when `DATABASE_URL` is set, else MemorySaver.
- [x] Run log (`run_log.py`) + `supabase/migrations/0001_run_log.sql`.
- [x] FastAPI surface (`main.py`): `POST /runs`, `POST /runs/{id}/respond`, `GET /runs/{id}`.
- [x] React + Vite frontend, three screens (`frontend/`).
- [x] Deterministic offline stubs — full run with no keys (`stubs.py`).
- [x] `run_local.py`, `demo_rescope_cap.py`; 18 tests green.

### a–g iteration pass
- [x] **a** — one-liner prompt spec: 12–25 words, lead with the layer function, grounded in retrieved text, ban marketing verbs / the company's own tagline.
- [x] **b** — Recon names the tier 1–3 outlets for the topic (`state.credible_outlets`); static host lists are a backstop; syndication independence check in `sources.assess_sources`.
- [x] **c** — tier-weighted corroboration (2.0 / 1.5 / 1.0, threshold `CORROBORATION_THRESHOLD` = 3.0) + `final_output.needs_review` bucket instead of a hard drop. *(Superseded in M1 — see "Corroboration model redesign" below; the review-queue bucket and the shape of the rule stayed, the tier-threshold gate itself didn't survive live testing.)*
- [x] **d** — one broadened-query retry (`search.reformulate_query`) before a layer is `no_results`.
- [x] **e** — add-layer button + editable layer definitions + optional "normalize my edits" one pass (`user_edit.normalize`, not charged to the cap).
- [x] **f** — thin rescope note → one free clarification round (2nd `interrupt()` in `confirm`), no attempt spent; client "did you mean a direct edit?" nudge.
- [x] **g** — drop-layer → "widen a sibling" prompt; per-layer soft target 12 / hard cap 25 + "layer too broad" warning.

### Repo
- [x] Private GitHub repo `AndradaP/market-map-agent`.
- [x] `dev` branch pushed; `main` gets README + PRD only for now.

---

## Next

### M1 — real pipeline  *(do roughly in order)*
- [ ] Get keys: Anthropic, Exa, LangSmith. Confirm a real run shows up in LangSmith with cost/latency.
- [x] **Real Execute path.** `search.find_company_sources`'s live branch used to
      just group search hits by domain. Now: search → `llm.extract_companies`
      (one call over all hits together, so one hit naming several companies and
      one company recurring across hits both get deduped in a single pass) →
      one independent `search.corroborate_company` search per extracted name,
      run in parallel (`company_corroboration_workers`), plus credit for
      whichever original hit(s) actually named the company
      (`layer_extract_cap`, `company_corroboration_results` in `config.py`).
- [x] **Real-key smoke tests.** Ran against live Anthropic + Exa keys across
      several topics; found and fixed 4 real bugs along the way: Exa 429s
      uncaught under nested layer×company concurrency (now retried with
      backoff), `extract_companies` omitting well-known companies' URLs,
      `resolve_url` getting 403'd by bot-protection with no browser
      User-Agent, and `draft_proposal` responses sometimes missing a required
      key with no default.
- [x] **Corroboration model redesign.** Live runs across 3+ topics showed
      *nothing* ever scored above 2.0 against the old tier-weighted 3.0
      threshold, and digging in showed the real bottleneck was the curated
      "credible outlets" tier list itself — it doesn't generalize across
      fields (chemistry vs. CPG vs. AI infra don't share a press corps), and
      recon-supplied per-topic outlets could be wrong (`github.com` got named
      tier-3 for a dev-tools topic). Replaced the tier-threshold gate with a
      simple independent-*source-count* rule (`sources.assess_sources`): ≥2
      distinct non-junk domains = corroborated, regardless of tier. Junk
      (never counts) is a short, field-agnostic list — the company's own
      domain, PR wires, code/package hosts, known low-signal aggregators.
      Tier data is kept as a display-only "featured in ..." badge. See
      `docs/PRD.md`'s Corroboration section for the full rationale.
- [ ] **Diagnostic batch against the new model** — run geothermal, AEO/GEO,
      neo-cloud, AI-native GTM, AI/LLM security, and AI infra to see how the
      count-based rule and Recon's per-topic outlet discovery hold up across
      genuinely different fields before tuning further.
- [ ] Prompt tuning, in this order: Propose (scope quality is the point) → company
      one-liners → category-fit → layer explanations. Add few-shot examples.
- [ ] Decide open question #1 (structured clarifying questions vs strings) once
      there are real proposals to look at.

### M2 — product surface
- [ ] `npm install` + run the frontend against a live FastAPI backend.
- [ ] Verify the interrupt/resume round-trips survive going over HTTP — including
      the clarification round (two interrupts in one node).
- [ ] Point `DATABASE_URL` at the Supabase project; run `0001_run_log.sql`;
      confirm PostgresSaver checkpointing + the run-log insert work against real
      Postgres (only MemorySaver / jsonl are exercised today).
- [ ] Deploy: Dockerfile + backend on Railway or Render; frontend on Vercel.

### M3 — eval
- [ ] Eval harness that reads the run log.
- [ ] Metrics: scope quality (human-rated), company precision, source-tier
      distribution, rejection rate by reason.
- [ ] Decide open question #2: run-log cost/token backfill — async patch from
      LangSmith by `run_id` vs. local tally from API responses.

### Later / nice-to-have
- [ ] Promote per-layer research from the thread pool → LangGraph `Send` fan-out
      (per-layer tracing + checkpointing). Noted in `execute.py`.
- [ ] Diagram view of the map (stretch; structured data is the v1 deliverable).
- [ ] Cheaper model for the mechanical steps (Groq / Together) — only if LangSmith
      shows it's actually a cost or latency problem.
- [ ] Per-run / monthly spend cap — flagged, deferred. Decide: refuse-to-start
      vs. stop-mid-run; ties into the LangSmith cost data.

---

## Open decisions  *(full write-ups in `OPEN_DECISIONS.md`)*
1. Propose's clarifying-question wording + structure; rescope-note gate thresholds.
2. Run-log cost/token backfill mechanism.
