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
- [x] Get keys: Anthropic, Exa, LangSmith. Confirmed real runs show up in LangSmith (this is also how the API-key leak below was found).
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
- [x] **Diagnostic batch against the new model** — ran geothermal, AEO/GEO,
      neo-cloud, AI-native GTM, AI/LLM security, and AI infra against live
      keys. Found the count-based rule (above) traded one failure mode for a
      worse one in spam-dense fields: AEO/GEO's swarm of small, near-identical
      content-farm domains cleared the mechanical ≥2-source gate undetected,
      and in AI infra a domain that was actually listed on a security
      phishing/malware blocklist scored as "independent coverage." Neither is
      a corroboration-quality nitpick — the second one is a real trust/safety
      problem for a tool that vouches for companies.
- [x] **Harden against spam and threat-intel hits.** `sources.assess_sources`
      now hard-vetoes any source matching a threat-intel/blocklist pattern,
      regardless of what else was found. Added `llm.plausibility_check`: one
      cheap LLM sanity pass, applied only to the small shortlist that already
      cleared the mechanical gate (not every candidate), asking whether the
      sources read as genuine coverage or generic content-farm noise —
      fails *open* on any error so a hiccup in this bonus check can never
      bury a company the real gate already accepted. Also fixed two real
      host-matching bugs found in the same batch: multi-TLD self-promotion
      (`teravolt.jp`/`.trading` counting as independent from `teravolt.com`)
      and subdomains of a junk host not matching it (`uk.linkedin.com` vs
      `linkedin.com`) — both are now suffix-aware.
- [x] **Manual review pass — five root causes, not isolated bugs.** A close
      read of real output (not just metrics) across the diagnostic batch
      surfaced: (1) no canonical company identity across layers/runs, causing
      cross-layer duplicates (~15% of one run's entries) and the same real
      company scoring inconsistently run-to-run purely from search luck
      (Nscale: 4 sources under one topic, 1 under an adjacent one); (2)
      `extract_companies`'s definition of "company" was underspecified —
      products/regulations got extracted as if they were vendors (`Gemini`,
      `EU AI Act`), and real companies mentioned only as a comparison inside
      someone else's coverage were missed (`Profound`, `Bluefish AI` —
      confirmed present in the retrieved text, never promoted to candidates);
      (3) Propose left two universal scoping questions (services vs. product
      vendors; incumbents vs. emerging players) to accident instead of an
      explicit decision; (4) existence verification was a single, one-shot,
      binary gate blind to corroboration strength — a well-corroborated real
      company (Fervo Energy, 7 independent sources) got hard-rejected purely
      because its site's bot protection 403'd a plain HTTP client; (5) no
      persistent memory of a company across runs/topics (see registry below).
      Fixed (1)-(4): `synthesize._dedupe_across_layers` (canonical-host merge,
      keeps the best-status instance run-wide), a tightened extraction
      prompt (excludes products/regulations, extracts comparison-only
      mentions, canonicalizes to the fullest name form seen), Propose's
      prompt now requires stating both scoping decisions explicitly, and
      `resolve_url` retries transient network errors once + `verify_node`
      no longer lets an ambiguous 403/429 override a company that already
      cleared corroboration (downgrades to review queue instead of
      hard-rejecting a weakly-corroborated one still gets rejected as before).
      Confirmed live: rerunning geothermal after these fixes went from 8
      duplicated companies (of 75 entries) to 0, and Fervo Energy correctly
      moved from rejected to the review queue.
- [x] **Persistent cross-run company registry** (root cause #5 above).
      `registry.merge_and_store` keys a company by canonical host and
      accumulates every independent source ever found for it across every
      run/topic instead of starting from zero each time; also settles on the
      fullest name form ever seen (fixes `Together`/`Together AI`
      oscillation). Falls back to a local JSON file when no `DATABASE_URL` is
      set; no-op pass-through in stub mode. Migration:
      `supabase/migrations/0002_company_registry.sql`. Confirmed working
      against a live Supabase Postgres instance (see M2 below).
- [x] **Security: API keys were leaking into LangSmith trace data.** Found
      while reviewing a trace pulled for the registry work: every
      `@traceable` llm.py/search.py function takes a `Settings` object as an
      argument, and LangSmith's tracing serializes full function arguments by
      default — the Anthropic, Exa, and LangSmith API keys (plain `str`
      fields) were sitting in plaintext in stored trace data. All three keys
      were rotated immediately. Root-cause fix: `config.py`'s secret fields
      (`anthropic_api_key`, `exa_api_key`, `langsmith_api_key`,
      `database_url`) are now pydantic `SecretStr`, which masks as
      `**********` on repr/str/`model_dump_json` — the exact serialization
      path a tracer uses — unless code explicitly calls `.get_secret_value()`,
      which now happens only at the real client constructors. Locked in by
      `test_secrets_never_leak.py` so it can't regress silently. Tried to
      sanitize the already-exposed historical traces via the LangSmith API;
      it rejects edits to a completed run ("duplicate run update"), so that
      isn't possible — rotation is what actually neutralizes the exposure.
- [ ] Prompt tuning still open: company one-liners → category-fit → layer
      explanations (Propose's scope-decision prompting is done, above). Add
      few-shot examples.
- [x] **Open question #1 resolved** — `open_questions` is now structured
      (`{question, affects, options}`) instead of plain strings, and answerable
      in place in the UI (pick an option, it drafts the rescope note for you).
      Directly motivated by a live finding: a real user testing the confirm
      screen didn't know what "Guardrails" meant in a plain-string question
      and would've needed to look it up to answer it; a concrete pick-one
      choice tied to a visible layer doesn't require that. See
      `OPEN_DECISIONS.md` #1 and PRD.md §5/§6.

### M2 — product surface
- [x] **`npm install` + run the frontend against a live FastAPI backend.**
      First time ever — built early in M0, untouched since. Found and fixed
      real bugs along the way: the checkpointer connection-drop bug (below),
      and frontend UX gaps (no way to start over or go back once past the
      first screen; stale "tier-weighted source bar" copy; zoom level had no
      inline explanation). The interrupt/resume round-trip over HTTP works
      correctly, confirmed live, including the confirm/edit -> final-map path.
- [x] Verify the interrupt/resume round-trips survive going over HTTP —
      confirmed via the frontend smoke test above.
- [x] Point `DATABASE_URL` at the Supabase project; ran both migrations
      (`0001_run_log.sql`, `0002_company_registry.sql`); confirmed
      PostgresSaver checkpointing, the run-log insert, and the company
      registry all work against a real, live Postgres instance.
- [x] **Checkpointer connection-drop bug**, found running the live frontend
      test above: `PostgresSaver.from_conn_string()` opens one bare
      connection and holds it for the process's whole life; Supabase's
      pooler (or just idle network flakiness) dropped it after a few
      minutes, and every run after that hard-failed with "the connection is
      closed" (a raw 500 through the frontend) until the process restarted.
      Fixed by giving `PostgresSaver` a `psycopg_pool.ConnectionPool`
      instead of a bare connection — natively supported (see
      `langgraph.checkpoint.postgres._internal.Conn`) — which transparently
      discards a dead connection and serves a fresh one. Verified live:
      manually killed a connection the pool was holding mid-session; the
      next checkpoint operation succeeded anyway.
- [ ] Deploy: Dockerfile + backend on Railway or Render; frontend on Vercel.
      Not started — no hosting accounts/CLIs set up yet on this machine.

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
1. ~~Propose's clarifying-question wording + structure~~ — resolved, see M1 above. Rescope-note gate thresholds still untuned.
2. Run-log cost/token backfill mechanism.
