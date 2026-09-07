# Market Map Agent

Takes a topic — broad or narrow — and produces a **value-chain skeleton** with a
**market map** of real, source-verified companies at each layer. Reconnaissance
first, human confirms the scope, then real research budget per layer.

This repo is the **skeleton**: the full LangGraph loop is wired with all six
nodes, the rescope cap works for real, LangSmith tracing is on when a key is
present, and every LLM/search call has a deterministic **stub** so the whole
thing runs end to end offline.

## Layout

```
market-map-agent/
├── backend/
│   ├── app/
│   │   ├── config.py          # env settings (pydantic-settings)
│   │   ├── state.py           # the state schema — real TypedDicts
│   │   ├── graph.py           # StateGraph: 6 nodes + rescope back-edge + router
│   │   ├── nodes/             # recon · propose · confirm · execute · verify · synthesize
│   │   ├── llm.py             # Claude calls  (+ stub fallbacks)
│   │   ├── search.py          # Exa calls     (+ stub fallbacks)
│   │   ├── sources.py         # credibility tiering + 2-source corroboration rule
│   │   ├── stubs.py           # deterministic offline fixtures
│   │   ├── checkpointer.py    # Postgres checkpointer / MemorySaver
│   │   ├── run_log.py         # one row per completed run (the "memory")
│   │   ├── tracing.py         # LangSmith wiring
│   │   └── main.py            # FastAPI: POST /runs, POST /runs/{id}/respond, GET /runs/{id}
│   ├── scripts/
│   │   ├── run_local.py       # one full run, end to end, no network
│   │   └── demo_rescope_cap.py# drives 2 rescopes + refused 3rd + direct-edit takeover
│   └── tests/test_rescope_cap.py
├── frontend/                  # React + Vite, 3 plain screens (topic → review → map)
├── supabase/migrations/0001_run_log.sql
└── docs/OPEN_DECISIONS.md     # the brief's open decisions + my take on each
```

## Run it (offline, no keys)

```bash
cd market-map-agent
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

# one full run, printed as a nested list + the run-log row
.venv/bin/python -m backend.scripts.run_local "AI observability"

# the rescope cap, driven end to end
.venv/bin/python -m backend.scripts.demo_rescope_cap

# the cap logic under test
.venv/bin/python -m pytest backend/tests -q
```

`"AI observability"` has a hand-written fixture (5 layers, real company names,
one rejection of each kind). Any other topic gets a generic skeleton in stub
mode — run with real keys for substance.

## Run it for real

Copy `.env.example` → `.env`, fill in keys, set `USE_STUBS=false`.

| Key | Used for |
|---|---|
| `ANTHROPIC_API_KEY` | Propose + Synthesize (judgment model), recon queries + one-liners (mechanical model) |
| `EXA_API_KEY` | recon search, per-layer company discovery, URL resolution |
| `LANGSMITH_API_KEY` | tracing — every node call + every LLM/Exa call, with cost/latency/tokens |
| `DATABASE_URL` | Supabase Postgres: `market_map_runs` table **and** the LangGraph checkpointer |

If `ANTHROPIC_API_KEY` or `EXA_API_KEY` is missing the app silently falls back to
stubs (see `Settings.stubs_enabled`).

```bash
# apply the run-log migration (checkpointer tables are auto-created by PostgresSaver.setup())
psql "$DATABASE_URL" -f supabase/migrations/0001_run_log.sql

.venv/bin/uvicorn backend.app.main:app --reload      # :8000
cd frontend && npm install && npm run dev            # :5173, proxies /api -> :8000
```

## The loop

`START → recon → propose → confirm ─┐`
`                                   ├─ rescope (reuse recon) → propose`
`                                   ├─ rescope + "different topic" → recon`
`                                   └─ confirm / direct_edit → execute → verify → synthesize → END`

- **confirm** is a real durable pause — `interrupt()` suspends, `Command(resume=...)`
  continues. State survives a process restart via the checkpointer.
- **Rescope cap** (`RESCOPE_CAP`, default 2): after 2 rescope requests the agent
  refuses a 3rd automated pass, flips to direct-edit-only on the last proposal,
  and states why. The cap and remaining count are in the payload of the very
  first proposal, not discovered on hitting it.
- **Corroboration** is tier-weighted (`sources.assess_sources`): tier-1 = 2.0,
  tier-2 = 1.5, tier-3 = 1.0 per distinct independent source; a company must clear
  `CORROBORATION_THRESHOLD` (default 3.0) **and** have ≥ 2 sources. Company-owned
  pages and PR wires are "existence-only"; aggregators are excluded; near-identical
  headlines across hosts count once (syndication). Recon names the tier-1..3
  outlets for the topic (`state.credible_outlets`); the host lists in `sources.py`
  are only a backstop.
  - No tier-1..3 source → **rejected** (`failed_corroboration`).
  - Has sources but below threshold → **kept, flagged `under_corroborated`** →
    lands in `final_output.needs_review` for a human to rescue, not on the map.
- **Verify** does two separate checks: URL actually resolves (no fabricated URLs)
  + the grounded one-liner fits the layer's confirmed definition. Every rejection
  is carried into `final_output.rejected` with a stated reason.
- **Empty layer** → one broadened-query retry (`search.reformulate_query`) before
  it's marked `no_results`; the retry is flagged in the layer + warnings.
- **Per-layer volume**: soft target `LAYER_COMPANY_SOFT_TARGET` (12), hard cap
  `LAYER_COMPANY_HARD_CAP` (25). Over the hard cap → list truncated (best-
  corroborated kept) **and** a "layer too broad — consider splitting" warning.
- **Rescope-note gate**: a thin rescope note triggers one free clarification
  question (a 2nd `interrupt()` in `confirm`) that does **not** spend an attempt.
  The client also nudges ("this looks like a direct edit you can do for free").

## Deviations from the draft state schema

All additive, all noted in `state.py`:

1. `proposal.layer_definitions: {layer -> sentence}` — Verify's category-fit check
   needs each layer's stated definition; the draft only had layer names.
2. `proposal.notes: str` — Propose's honest caveat when recon is thin/contradictory
   (the brief asks for this behaviour).
3. `user_edit.edited_scope` — somewhere for a direct edit's payload to live.
4. Bookkeeping: `propose_attempts`, `cap_hit`, `force_direct_edit`,
   `handoff_message`, `run_id`, `metrics`.
5. `LayerResult.status` (`ok` / `no_results` / `no_verified_companies`) +
   `final_output.warnings` — honest handling of empty layers.
6. `Company.corroboration {status, score, tiers, detail}` + `final_output.needs_review`
   — tier-weighted corroboration and the under-corroborated review queue.
7. `state.credible_outlets` — Recon-identified tier-1..3 outlets for the topic.
8. `state.layer_meta` — per-layer `raw_count` / `reformulated` / `over_cap`.
9. `user_edit.normalize` — direct-edit flag for the one-pass name/order tidy.

## Iteration log — edits a–g (agreed with the brief owner)

| | Change | Where |
|---|---|---|
| a | One-liner prompt: 12–25 words, lead with the layer function, ban marketing verbs, ground every claim | `llm.company_one_liner` |
| b | Recon names the tier-1..3 outlets for the topic; static lists are a backstop; syndication independence check | `nodes/recon.py`, `llm.credible_outlets`, `sources.assess_sources` |
| c | Tier-weighted corroboration (2.0 / 1.5 / 1.0, threshold 3.0) + `needs_review` bucket instead of a hard drop | `sources.assess_sources`, `nodes/execute.py`, `nodes/synthesize.py` |
| d | One broadened-query retry before a layer is `no_results` | `search.reformulate_query`, `search.find_company_sources` |
| e | "Add layer" + editable definitions + "normalize my edits" (one cheap pass, not a rescope) | `frontend/src/App.jsx`, `llm.normalize_scope`, `nodes/confirm.py` |
| f | Thin rescope note → one free clarification round (no attempt spent) + client "did you mean a direct edit?" nudge | `nodes/confirm.py`, `frontend/src/App.jsx` |
| g | Drop-layer → "widen a sibling" prompt; per-layer soft target + hard cap with "too broad" warning | `frontend/src/App.jsx`, `nodes/execute.py`, `nodes/synthesize.py` |

## Not built yet (deliberately)

Real LLM prompt bodies are written to the right spec but untuned (no few-shot
examples, no eval loop yet). Parallel per-layer research uses a thread pool;
promoting it to LangGraph `Send` fan-out (for per-layer tracing/checkpointing) is
noted in `execute.py`. Run-log cost/tokens are `null` in stub mode — backfill
from LangSmith by `run_id` is the plan. Frontend is unstyled-minimal, not run
through `npm install` here. No deploy config.
