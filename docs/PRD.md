# Market Map Agent — PRD

**Status:** draft · **Last updated:** 2026-09-13

---

## 1. Problem

Value chains (the stages a space moves through) and market maps (who occupies
each stage) are normally produced separately, by hand, and go stale quickly.

- **Broad topics** — dozens of overlapping maps already exist; the work is
  reading and reconciling five analysts' takes.
- **Narrow / novel topics** — no map exists at all.

Automating this isn't blocked on *writing* — an LLM drafts a plausible structure
in one call. It's blocked on **scoping**. "Advanced air mobility" could
reasonably split into eVTOLs, ground infrastructure, certification, or batteries.
A one-shot answer picks one and is often wrong, and a wrong frame makes the whole
output untrustworthy.

## 2. What we're building

An agent that takes one topic string and returns a value-chain skeleton
populated with real, source-verified companies at each layer. It:

1. researches the space before assuming a scope,
2. proposes a bounded structure and has a human confirm or correct it,
3. spends per-layer research budget only after the scope is locked,
4. grounds every company placement in independent, credible sources,
5. writes one log row per run as an eval record.

The capability bar is identical for any topic — "agentic AI" or "produced water
treatment". No niche restriction.

**Value proposition.** Broad topics: speed and synthesis — one complete, sourced
map in minutes instead of a day of reading. Narrow topics: this may be the only
map that exists.

## 3. Goals / non-goals

### Goals (v1)
- One complete, sourced value chain + market map per topic, in minutes.
- A genuine reconnaissance → confirm → research loop with a real human gate.
- Every company: a verified URL, a grounded one-liner, and independent credible
  corroboration.
- Honest failure — no silent drops; thin or empty layers stated plainly.
- Structured-data output; run log persisted for later eval.

### Non-goals (v1)
- Polished visual / diagram rendering (structured data + a plain nested list
  first; a diagram view is a stretch goal).
- Sub-categorizing companies *within* a layer (folded into the one-liner as
  prose).
- Forcing a confident structure when recon is thin or contradictory — say so
  instead.
- Auth, multi-tenant, user accounts.
- Cost optimization via cheaper models — measure first.

## 4. User & flow

One user, a web form, no login (v1).

1. **Submit a topic.**
2. **Review the proposed structure.** Three affordances:
   - **Confirm as-is.**
   - **Direct edit** — rename / drop / add layers, edit a layer's definition,
     change the zoom level. No model call. Free and unlimited.
   - **Rescope request** — free-text "what's wrong", optional "this is actually a
     different topic" checkbox. Capped (§6). The model tries again.
3. **Receive the final map** — per layer: an explanation and its verified
   companies; plus a review queue (verified but under-corroborated) and a
   rejected list, each with reasons.

## 5. The loop — node contracts

| # | Node | In | Out |
|---|------|----|----|
| 1 | **Recon** | topic string | search results/snippets; the tier 1–3 outlets that are credible *for this topic* |
| 2 | **Propose** | recon results (+ rescope notes) | proposal: `layers`, `layer_definitions`, `in_scope`, `excluded_adjacent`, `zoom_level` (`component`/`company`/`category`), `open_questions`, honest `notes` — and now two scoping calls stated explicitly rather than left to accident: are generalist consulting/services firms in scope, and are large incumbents included alongside emerging players (see BACKLOG.md, "manual review pass") |
| 3 | **Confirm / edit** | the proposal | confirmed scope, **or** a routed edge back to Propose (or Recon, if "different topic"). A real pause — `interrupt()` suspends, `Command(resume=…)` continues. |
| 4 | **Execute** | confirmed scope | raw candidates per layer — name, claimed URL, corroborating sources, independent-source-count corroboration verdict (see §6). Each candidate is first merged against the persistent company registry (cross-run accumulated evidence, keyed by domain) before scoring. Parallel across layers. |
| 5 | **Verify** | raw candidates | per company: existence & identity check (URL resolves — a 403/429 on a company that already cleared corroboration downgrades to the review queue rather than hard-rejecting, since that's an ambiguous bot-block signal, not proof the company is fake; grounded one-liner from retrieved text) **and** category-fit check (one-liner vs the layer's confirmed definition). Failures kept with a reason. |
| 6 | **Synthesize** | confirmed scope + verified layers | cross-layer dedup first (the same company independently found by more than one layer is merged by canonical host, kept once at its best status — not shown as a duplicate); final map (structured); write the run-log row |

## 6. Rules

### Rescope cap
- ≤ 2 model rescope requests (3 Propose attempts total). The cap and remaining
  count appear on the **first** proposal screen, not on hitting it.
- A rescope reuses the existing recon results — one more LLM call, no new search
  — unless the user ticks "this is actually a different topic", which triggers
  fresh Recon.
- On the cap: no third automated pass. Switch to direct-edit-only on the last
  proposal and state why ("We've tried scoping this twice — over to you").
- If a rescope note is too thin to act on, the gate asks **one** clarifying
  question first; that round does not spend an attempt.

### Source credibility — a tiered typology, not a fixed name list
- **Tier 1 — primary & authoritative:** regulators / government bodies, standards
  bodies, peer-reviewed journals.
- **Tier 2 — established press & research houses:** major business press, free
  reports from the large consultancies and research firms.
- **Tier 3 — trade press & informed newsletters:** vertical trade journals,
  credible VC blogs/newsletters. Startup-adjacent sources (YC, Crunchbase, trade
  newsletters) live here — tier 3, not universal tier 1.
- **Existence-only:** a company's own site or press release, PR wires. Confirms
  what a company claims; never counts as corroboration.
- **Excluded:** scraped / republished "free market research" aggregator sites.
  Don't count at all.
- Recon identifies which *named* outlets fill tiers 1–3 for the topic at hand.
  The static host lists in code are only a backstop.

### Corroboration
*(Revised post-M1 live testing — see BACKLOG.md. Originally a tier-weighted
score against a 3.0 threshold; live runs across several topics showed the
tier allowlist doesn't generalize across fields — chemistry, CPG and AI infra
don't share a press corps — so the gate is now independent-source **count**,
not a curated "credible outlet" judgment.)*
- ≥ 2 distinct, non-junk domains mentioning the company → **corroborated**,
  placed on the map. Any domain counts, tiered or not — a niche newsletter or
  a VC portfolio page with no hand-curated tier is still a real, independent
  mention. Near-identical headlines across hosts (a syndicated wire story)
  count once, not twice.
- "Junk" (never counts, at any count): the company's own domain, PR wires,
  code/package hosts, and known low-signal aggregators — this list is short
  and holds across any field, unlike a "credible outlets" allowlist.
- Exactly 1 independent source → **review queue** — a human promotes or drops it.
- 0 independent sources → **rejected**.
- Tier data (tier 1/2/3, per the original typology) is still computed and
  shown as a "featured in ..." display badge — it no longer gates anything.
- **Threat-intel hard veto** (found live: a domain that was actually listed on
  a security phishing/malware blocklist was scoring as "independent coverage"):
  any source matching a known blocklist pattern disqualifies the company
  outright, regardless of what else was found.
- **Plausibility sanity pass** (found live: dense spam/content-farm swarms in
  some fields cleared the mechanical gate undetected): one cheap LLM check,
  applied only to the small shortlist that already passed, asking whether the
  sources read as genuine coverage or generic noise. Fails *open* on any
  error — a hiccup here can never bury a company the real gate already
  accepted.
- **Cross-run company registry**: every independent source ever found for a
  company (keyed by canonical domain) accumulates across every run and topic,
  Postgres-backed, instead of each run starting from zero. Also settles on the
  fullest name form ever seen for a company across runs.

### Verification — two separate checks
- **Existence & identity** — the URL resolves to that company (a plausible but
  fabricated URL is worse than none). Write a one-line description from what was
  actually retrieved, not inferred from the name.
- **Category fit** — check that one-liner against the layer's confirmed
  definition; reject the placement if it doesn't belong, even for a real,
  accurately-described company.
- Every rejection (failed corroboration, existence, or category fit) is visible
  in the output with a stated reason.

### Empty / thin layers
- One broadened-query retry before a layer is marked empty.
- Then keep the layer in the map with status `no_results` or
  `no_verified_companies` and a warning — never drop it.
- All layers empty → a warning that the scope is probably wrong; suggest a
  rescope.

### Per-layer company volume
- Soft target ~12 per layer; hard cap ~25.
- Over the hard cap → keep the best-corroborated, and warn "this layer is
  probably too broad — consider splitting it". Never a silent truncation.

## 7. Output

`final_output`:

```
topic, zoom_level, generated_at
layers[]:      name, explanation, status, companies[], under_corroborated_count,
               reformulated, over_cap
needs_review[]: companies verified but under-corroborated  (name, layer, one_liner, corroboration)
rejected[]:     failed a hard check  (name, layer, rejection_reason)
warnings[]
```

`company`: `name`, verified `url`, `one_liner`, `sources[]`,
`corroboration {status, score, tiers}`.

## 8. Memory / logging

One row per completed run, written once at the end: topic, confirmed-scope
summary, layer count, companies found / verified / under-corroborated, rejections
split by reason (corroboration / category fit / existence), reformulated and
over-cap layer counts, rescope count and whether the cap fired, cost, token
count, latency, timestamp.

This is a deliberate thin log — an eval dataset, not a knowledge base. It lives
in Supabase Postgres alongside the LangGraph checkpointer: shared database,
separate concerns. The checkpointer is infrastructure (it makes the confirm-step
pause durable across processes); the run log is the intentional record.

## 9. Architecture

- LangGraph state machine; `interrupt()` / `Command(resume=…)` for the gate.
- FastAPI wraps the compiled graph: `POST /runs`, `POST /runs/{id}/respond`,
  `GET /runs/{id}`.
- Postgres checkpointer for durable pause/resume (MemorySaver offline). Wired
  to a live Supabase Postgres instance and confirmed working — not just the
  design intent — alongside the run log and the company registry, which share
  the same database.
- React + Vite frontend — three screens. **Never run against the live
  backend** (built early, untouched since); `npm install` alone is unverified.
- LangSmith tracing active whenever `LANGSMITH_API_KEY` is set; every node call
  and every LLM/Exa call is a span. Secret `Settings` fields are pydantic
  `SecretStr` specifically because this tracing serializes full function
  arguments by default — a plain-`str` API key field leaked into stored trace
  data live (see BACKLOG.md); all Settings secrets were converted after
  rotating the exposed keys.
- Deterministic offline stubs for every LLM/search call, so the loop runs with no
  keys.

### Hosting
Frontend on Vercel. Backend needs an always-on host (Railway / Render / Fly) —
runs are long and pause mid-execution, which serverless does not handle well.

## 10. Milestones

| | Milestone | Contents |
|---|---|---|
| **M0** | Skeleton *(done)* | Full loop wired, rescope cap, tracing, checkpointer, run log, FastAPI, frontend, offline stubs, tests. |
| **M1** | Real pipeline | Live keys; real Exa company extraction (name + URL, not domain grouping); prompt tuning starting with Propose; first real runs. |
| **M2** | Product surface | Frontend against a live backend; Supabase wired; deploy. |
| **M3** | Eval | Harness off the run log; iterate scope quality and company precision. |

## 11. Open questions

1. **Clarifying questions.** Exact wording and structure of Propose's
   `open_questions` and the rescope-note clarification copy — worth a review pass
   before it's load-bearing. Candidate change: structured
   `{question, affects: layers|scope|zoom, options?}` instead of plain strings so
   the UI can place each question next to the control it affects.
2. **Run-log cost/tokens.** Backfill from LangSmith by `run_id` a few seconds
   after the row is written, vs. tallying token counts locally from the Anthropic
   responses as the run goes.
