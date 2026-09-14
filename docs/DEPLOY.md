# Deploying the public demo

The public link runs in **stub mode** — deterministic, offline, zero API cost.
Anyone with the link gets the full UI/UX (topic → proposal → confirm/edit →
final map) with no risk of burning your Anthropic/Exa credits. Live-key runs
stay local, for your own demos.

Two pieces, deployed separately: backend (FastAPI) on Railway, frontend
(React/Vite) on Vercel.

## 1. Backend — Railway

1. [railway.app](https://railway.app) → sign in with GitHub → **New Project**
   → **Deploy from GitHub repo** → pick `AndradaP/market-map-agent`.
2. Railway auto-detects Python via `requirements.txt` and the root
   [`Procfile`](../Procfile) (`web: uvicorn backend.app.main:app --host 0.0.0.0
   --port $PORT`) — no build config needed.
3. Set exactly one environment variable under the service's **Variables** tab:
   ```
   USE_STUBS=true
   ```
   Leave `ANTHROPIC_API_KEY`, `EXA_API_KEY`, `LANGSMITH_API_KEY`, and
   `DATABASE_URL` unset. Without a `DATABASE_URL` the checkpointer falls back
   to in-memory (per the `build_checkpointer` branch in
   `backend/app/checkpointer.py`) and the run log / company registry no-op —
   fine for a stub-only demo; state just doesn't survive a restart.
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
