# Deploying the public demo

The public link runs **real** Anthropic + Exa keys — a stub-only demo shows
the UI but not the thing this project is actually about (real, source-verified
companies). To keep that affordable with strangers on the link, a daily cap
gates it before a single dollar is spent: see [rate_limit.py](../backend/app/rate_limit.py)
— per-IP (one visitor can't eat the whole day's budget) plus a global
backstop (in case of IP rotation), both enforced in `POST /runs` before the
graph is invoked. Recommended starting point: 2/day per IP, ~10-20/day
global — cheap even in the worst case, and "I don't expect a lot of users"
makes the realistic case cheaper still.

Two pieces, deployed separately: backend (FastAPI) on Railway, frontend
(React/Vite) on Vercel.

## 1. Backend — Railway

1. [railway.app](https://railway.app) → sign in with GitHub → **New Project**
   → **Deploy from GitHub repo** → pick `AndradaP/market-map-agent`.
2. Railway auto-detects Python via `requirements.txt` and the root
   [`Procfile`](../Procfile) (`web: uvicorn backend.app.main:app --host 0.0.0.0
   --port $PORT`) — no build config needed.
3. Set these environment variables under the service's **Variables** tab:
   ```
   USE_STUBS=false
   ANTHROPIC_API_KEY=<your real key>
   EXA_API_KEY=<your real key>
   DAILY_RUN_LIMIT_PER_IP=2
   DAILY_RUN_LIMIT_GLOBAL=15
   ```
   `LANGSMITH_API_KEY` and `DATABASE_URL` are optional — leave both unset for
   the simplest deploy. Without a `DATABASE_URL` the checkpointer falls back
   to in-memory (per the `build_checkpointer` branch in
   `backend/app/checkpointer.py`) and the run log / company registry no-op;
   fine for a demo, just means state doesn't survive a restart and the rate
   limit counters reset on redeploy too (in-memory, see `rate_limit.py`).
   Set `DATABASE_URL` to the same Supabase instance from local dev if you want
   the registry/run-log to persist across restarts — the rate limiter itself
   stays in-memory either way, by design (see its module docstring).
4. Deploy. Railway gives you a public URL like
   `https://market-map-agent-production.up.railway.app`. Sanity check:
   ```
   curl https://<your-railway-url>/docs
   ```
   should return the FastAPI Swagger page.

## 2. Frontend — Vercel

1. [vercel.com](https://vercel.com) → sign in with GitHub → **Add New Project**
   → same repo → set **Root Directory** to `frontend`.
2. Framework preset: Vite (auto-detected). Build command / output dir: leave
   defaults (`npm run build`, `dist`).
3. Add one environment variable:
   ```
   VITE_API_BASE=https://<your-railway-url>
   ```
   (`frontend/src/api.js` reads this at build time; no code change needed.)
4. Deploy. Vercel gives you the public frontend URL — that's the link to
   share.

## 3. After it's live

- Update [README.md](../README.md) — replace "Not deployed" with the live
  link, and note it runs in stub mode.
- Re-check CORS: `backend/app/main.py` currently allows `allow_origins=["*"]`,
  which is fine for a read-only public stub demo; tighten to the Vercel origin
  only if this ever carries real keys or write-heavy traffic.
- Nothing here is a one-way door — Railway/Vercel redeploy automatically on
  push to `main`, so iterating after the first deploy is just `git push`.
