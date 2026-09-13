# Andra's Market Map Agent

A significant part of my role as Innovation Associate consists of conducting needfinding with corporate venture partners around their companies' innovation priorities and sourcing pilot-ready startups they can deploy to bolster operations or meet EGS goals.

Building **value chains** (the stages a space moves through) and **market maps** (real companies at each stage) are exercises I've gone through to better understand where different tech is today and where it's headed.  
  
The purpose of this agent is to produce a strong first pass to speed up research when analyzing a market and its players. Give it a topic, broad or narrow ("advanced air mobility", "AI observability", "geothermal energy"), and it returns a **value chain** populated with a **market map** of companies verified by independent sources. 

Scoping and building the value chain is the first bottleneck I've identified, while researching companies follows from a well-scoped framework and can be automated agentically. This agent researches the space first, has a human-in-the-loop confirm or correct the proposed structure, and grounds every company in independently-verified sources before it ships.

## How it works

A six-node [LangGraph](https://langchain-ai.github.io/langgraph/) loop:


| Node               | Does                                                                                                                                                                                                                                                                                               |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Recon**          | Broad web search (Exa) on the raw topic. Also names outlets that look credible for this space (a hint, not a gate — see Corroboration below).                                                                                                                                                      |
| **Propose**        | Claude drafts a bounded structure: layers + definitions and what's in/out of scope for the market map, a zoom level, open questions, and which kinds of entries should populate the market map — are large incumbents and service companies included alongside emerging players. |
| **Confirm / edit** | Human-in-the-loop gate. Confirm, edit fields directly (free, unlimited), or ask the model to rescope (capped at 2 interactions). A real pause via LangGraph `interrupt()`.                                                                                                                         |
| **Execute**        | Per-layer company research in parallel: search → LLM extraction (dedupes repeat mentions, canonicalizes name variants, catches companies named only as a comparison inside someone else's coverage) → independent per-company corroboration search.                                                |
| **Verify**         | Existence (URL resolves) and category fit (does the one-liner actually belong in this layer).                                                                                                                                                                                                      |
| **Synthesize**     | Cross-layer dedup (the same company found independently by two layers is merged, not shown twice), then assembles the final map. Nothing gets dropped silently: rejections and under-corroborated candidates are surfaced with reasons.                                                            |




## Corroboration — the part that got iterated upon from live evidence

How might we trust outputs and avoid "AI slop" when building market maps across different industries? Each company or player that shows up on the market map is verified using **≥2 independent, non-junk sources**. "Junk" is defined as a short, field-agnostic list, including a company's own domain, PR wires, code/package hosts, which holds up across any field, unlike an infinite "credible outlets" list ever could.

How might we trust these sources are secure and won't let SEO-swarm content-farm domains through undetected? Sources are checked against known threat-intel/blocklist patterns, and companies that clear the mechanical gate get one further, cheap LLM sanity pass asking whether the sources read as real coverage or generic noise. That check applies only to the small shortlist that already passed, so it stays inexpensive, and it fails *open* to never bury a company on its own hiccup.

A closer manual read of real outputs (not just metrics) surfaced a further layer of findings: the same real company was getting extracted independently by more than one layer and shown as a duplicate; the same company could score well under one topic and poorly under an adjacent one purely from search luck. Fixed with a canonical-URL dedup pass at Synthesize and a **persistent, cross-run company registry** (Postgres) that accumulates every independent
source ever found for a company, keyed by domain, instead of starting from
zero every single run.

Full write-up of the reasoning and the live-run evidence behind each change is  
in [docs/PRD.md](docs/PRD.md) and [docs/BACKLOG.md](docs/BACKLOG.md).



## Stack


| Layer                 | Choice                                                                                                                          |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Orchestration         | LangGraph (Python) — native `interrupt`/`resume` for the gate                                                                   |
| LLM — judgment        | Claude (`claude-opus-5`) — Propose, Synthesize                                                                                  |
| LLM — mechanical      | Claude (`claude-sonnet-5`) — recon queries, extraction, one-liners, fit checks, the plausibility sanity pass                    |
| Search / verification | Exa                                                                                                                             |
| Observability         | LangSmith — per-node trace, cost, latency                                                                                       |
| Backend               | FastAPI                                                                                                                         |
| Database              | Supabase Postgres — run log, LangGraph checkpointer, company registry (all wired and confirmed working against a live instance) |
| Frontend              | React + Vite                                                                                                                    |




## Status

The full loop is real and has been run against live Anthropic + Exa keys across a dozen topics spanning very different fields (energy, AI infrastructure, dev tools, security, SEO-adjacent markets), not just smoke-tested once. Corroboration, extraction, and the scope contract have all been revised at least once based on that live evidence, not just designed up front. 70+ tests passing.

**Not yet done:** the React frontend has never been run against the live
backend (built early, untouched since) — `npm install` alone is unverified.
Prompt tuning for one-liners/category-fit is still open. Not deployed.

See [docs/PRD.md](docs/PRD.md) for the full spec and
[docs/BACKLOG.md](docs/BACKLOG.md) for the complete history of what changed
and why.

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

# a full run, offline, no keys
.venv/bin/python -m backend.scripts.run_local "AI observability"

# tests
.venv/bin/python -m pytest backend/tests -q
```

For a real run: copy `.env.example` → `.env`, add `ANTHROPIC_API_KEY` and
`EXA_API_KEY` (optionally `LANGSMITH_API_KEY`, `DATABASE_URL` for a Postgres
run log/checkpointer/registry instead of local files), and set
`USE_STUBS=false`.

```bash
.venv/bin/uvicorn backend.app.main:app --reload      # API on :8000
cd frontend && npm install && npm run dev            # form on :5173 -- unverified, see Status
```



## Layout

```
backend/app/         state schema, graph, six nodes, llm/search/sources/registry, FastAPI
backend/scripts/     run_local.py, demo_rescope_cap.py
backend/tests/       70+ tests
frontend/            React + Vite -- topic input -> proposal review -> map (untested against live backend)
supabase/migrations/ run-log table, company registry table
docs/PRD.md          product spec + full corroboration-model rationale
docs/BACKLOG.md       complete history: what shipped, what broke live, what changed and why
```

