# Market Map Agent

Give it a topic — broad or narrow ("advanced air mobility", "AI observability",
"produced water treatment") — and it returns a **value chain** (the stages a
space moves through) populated with a **market map** (the real companies at each
stage), every placement grounded in verified sources.

The hard part isn't generation, it's **scoping**. A one-shot prompt guesses a
structure and is often wrong, which makes the whole output untrustworthy. This
agent researches the space first, proposes a bounded structure, has a human
confirm or correct it, and only then spends research budget per layer.

## How it works

A six-node [LangGraph](https://langchain-ai.github.io/langgraph/) loop:

| Node | Does |
|------|------|
| **Recon** | Broad web search (Exa) on the raw topic. Also names the credible outlets (tier 1–3) for this space. |
| **Propose** | Claude drafts a bounded structure: layers + definitions, in-scope vs excluded-adjacent, a zoom level, and any genuinely open questions. |
| **Confirm / edit** | Human-in-the-loop gate. The user confirms, edits fields directly (free, unlimited), or asks the model to rescope (capped). A real pause via LangGraph `interrupt()`. |
| **Execute** | Per-layer company research, parallel, with tier-weighted source corroboration. |
| **Verify** | Two checks per company: the URL actually resolves (no fabricated links) and the grounded one-liner fits the layer's definition. |
| **Synthesize** | Assemble the final map — per layer: an explanation plus verified companies. Nothing is dropped silently; rejections and under-corroborated candidates are surfaced with reasons. |

Design points:

- **Rescope cap** — the model gets at most 2 rescope attempts, stated up front on
  the first proposal. On the cap it hands back to direct editing and says why. A
  too-thin rescope note gets one free clarifying question, no attempt spent.
- **Tier-weighted corroboration** — authoritative sources count more; a company
  below the bar is flagged for human review rather than dropped. No tier 1–3
  source at all → rejected, with the reason shown.
- **Honest failure** — an empty layer gets one broadened retry, then stays in the
  map with a plain status. Every rejection carries a stated reason.

## Stack

| Layer | Choice |
|---|---|
| Orchestration | LangGraph (Python) — native `interrupt`/`resume` for the gate |
| LLM — judgment | Claude (`claude-opus-5`) — Propose, Synthesize |
| LLM — mechanical | Claude (`claude-sonnet-5`) — recon queries, one-liners, fit checks |
| Search / verification | Exa |
| Observability | LangSmith — per-node trace, cost, latency |
| Backend | FastAPI |
| Database | Supabase Postgres — run log + LangGraph checkpointer |
| Frontend | React + Vite |

## Status

Early. The full loop is wired and runs end to end. It ships with deterministic
offline fixtures, so it runs with no API keys. The real-service paths (LLM
prompts, Exa company extraction) are built but not yet tuned. Not deployed.

See [`docs/PRD.md`](docs/PRD.md) for the full scope.

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

# a full run, offline, no keys
.venv/bin/python -m backend.scripts.run_local "AI observability"

# tests
.venv/bin/python -m pytest backend/tests -q
```

For a real run: copy `.env.example` → `.env`, add `ANTHROPIC_API_KEY` and
`EXA_API_KEY` (optionally `LANGSMITH_API_KEY`, `DATABASE_URL`), and set
`USE_STUBS=false`.

```bash
.venv/bin/uvicorn backend.app.main:app --reload      # API on :8000
cd frontend && npm install && npm run dev            # form on :5173
```

## Layout

```
backend/app/         state schema, graph, six nodes, llm/search/sources, FastAPI
backend/scripts/     run_local.py, demo_rescope_cap.py
backend/tests/
frontend/            React + Vite — topic input → proposal review → map
supabase/migrations/ run-log table
docs/PRD.md          product spec
```
