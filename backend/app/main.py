"""FastAPI surface for the web form. Thin wrapper over the LangGraph app that
supports the pause/resume gate.

    POST /runs                 {topic}            -> {run_id, status: "running"}
    POST /runs/{id}/respond    {type, notes, ...} -> {run_id, status: "running"}
    GET  /runs/{id}                               -> job status, then the result

Work runs in a background thread and the client polls, rather than the client
holding one HTTP request open for the duration. The research pass makes
thousands of network calls (a corroboration search, a URL fetch, a one-liner
and a category-fit check per company, across every layer) and takes minutes.
Held as a single request that died repeatedly in production: the browser gave
up, and the user saw a network error with no way to recover a run the server
had already paid for. Polling makes a dropped connection, a closed laptop and
a redeploy all survivable, and lets the client show the phase the run is
actually in instead of guessing from elapsed time.
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from langgraph.types import Command
from pydantic import BaseModel

log = logging.getLogger(__name__)

# run_id -> job record. In-memory on purpose: it mirrors graph state that the
# checkpointer already owns, so losing it on restart costs the phase label,
# not the run (when the checkpointer is Postgres-backed).
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()

from .checkpointer import build_checkpointer
from .config import get_settings
from .graph import build_graph
from .rate_limit import RateLimitExceeded, check_and_record, client_ip, usage
from .tracing import configure_tracing

_ctx: Dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    tracing_on = configure_tracing(settings)
    cp = build_checkpointer(settings)
    _ctx["checkpointer"] = cp
    _ctx["graph"] = build_graph(cp.saver)
    _ctx["meta"] = {
        "stubs_enabled": settings.stubs_enabled,
        "tracing_on": tracing_on,
        # What's actually in use, not what was configured. Those differ when
        # Postgres was set but unreachable, and a silent downgrade to
        # in-memory is exactly the kind of thing that's baffling weeks later.
        "checkpointer": "memory" if cp.degraded else settings.checkpointer_backend,
        "checkpointer_degraded": cp.degraded or None,
        "rescope_cap": settings.rescope_cap,
    }
    try:
        yield
    finally:
        cp.close()


app = FastAPI(title="market-map-agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateRun(BaseModel):
    topic: str


class RespondBody(BaseModel):
    # "none" | "direct_edit" | "rescope_request" | "rescope_clarification"
    type: str = "none"
    notes: str = ""
    different_topic: bool = False
    edited_scope: Optional[Dict[str, Any]] = None


def _interrupt_payload(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    intr = result.get("__interrupt__")
    if not intr:
        return None
    first = intr[0] if isinstance(intr, (list, tuple)) else intr
    return getattr(first, "value", first)


def _run_job(run_id: str, graph_input: Any, cfg: Dict[str, Any]) -> None:
    """Drive the graph to its next stopping point, recording which node is
    running as it goes. Streamed rather than invoked so `phase` is the node
    actually executing, not an inference from how long we've been waiting."""
    job = _jobs[run_id]
    try:
        review = None
        for chunk in _ctx["graph"].stream(graph_input, cfg, stream_mode="updates"):
            if not isinstance(chunk, dict):
                continue
            for node, payload in chunk.items():
                if node == "__interrupt__":
                    review = _interrupt_payload({"__interrupt__": payload})
                else:
                    job["phase"] = node
        if review is not None:
            job.update(status="awaiting_confirmation", review=review, phase=None)
            return
        values = _ctx["graph"].get_state(cfg).values
        job.update(
            status="complete",
            final_output=values.get("final_output"),
            metrics=values.get("metrics"),
            phase=None,
        )
    except Exception as exc:  # noqa: BLE001 -- surfaced to the client, not swallowed
        log.exception("run %s failed", run_id)
        job.update(status="error", error=f"{type(exc).__name__}: {exc}", phase=None)


def _start_job(run_id: str, graph_input: Any, cfg: Dict[str, Any]) -> Dict[str, Any]:
    with _jobs_lock:
        existing = _jobs.get(run_id)
        if existing and existing["status"] == "running":
            return existing  # already in flight; a double-click must not fork it
        _jobs[run_id] = {
            "status": "running",
            "phase": None,
            "review": None,
            "final_output": None,
            "metrics": None,
            "error": None,
            "started_at": time.time(),
        }
    threading.Thread(target=_run_job, args=(run_id, graph_input, cfg), daemon=True).start()
    return _jobs[run_id]


def _job_view(run_id: str, job: Dict[str, Any], maps: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out = {
        "run_id": run_id,
        "status": job["status"],
        "phase": job.get("phase"),
        "elapsed_s": round(time.time() - job["started_at"], 1),
        "maps": maps,
    }
    for key in ("review", "final_output", "metrics", "error"):
        if job.get(key) is not None:
            out[key] = job[key]
    return out


def _maps_counter(request: Request, settings) -> Dict[str, Any]:
    """What the header's 'map 2 of 3 today' counter reads from. The owner
    bypass skips the limiter entirely, so it reports as unlimited rather
    than counting toward a cap that will never fire for them."""
    if _is_owner(request, settings):
        return {"used": None, "limit": None, "owner": True}
    return {**usage(client_ip(request), settings), "owner": False}


@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    settings = get_settings()
    return {
        "ok": True,
        **_ctx.get("meta", {}),
        # Diagnostic only -- never the token/limit *values* being wrong in a way
        # that's hard to see from outside, just whether they're configured at
        # all. Real debugging aid after "the owner bypass isn't working".
        "daily_run_limit_per_ip": settings.daily_run_limit_per_ip,
        "daily_run_limit_global": settings.daily_run_limit_global,
        "owner_bypass_configured": bool(settings.rate_limit_bypass_token),
    }


def _is_owner(request: Request, settings) -> bool:
    token = settings.rate_limit_bypass_token
    return bool(token) and request.headers.get("x-owner-token") == token.get_secret_value()


@app.post("/runs")
def create_run(body: CreateRun, request: Request) -> Dict[str, Any]:
    settings = get_settings()
    if not _is_owner(request, settings):
        try:
            check_and_record(client_ip(request), settings)
        except RateLimitExceeded as exc:
            raise HTTPException(
                429,
                f"Daily demo limit reached ({exc.scope}: {exc.limit}/day). Try again tomorrow.",
            )
    run_id = uuid4().hex
    cfg = {"configurable": {"thread_id": run_id}}
    job = _start_job(run_id, {"topic": body.topic, "run_id": run_id}, cfg)
    return _job_view(run_id, job, _maps_counter(request, settings))


def _is_fresh_map_request(body: RespondBody) -> bool:
    """A 'different topic' rescope re-runs Recon + Propose from scratch --
    the same cost profile as POST /runs, just entered from inside an
    existing run instead of the topic screen. Without this, it's a free
    way around the daily cap: narrow the same topic all you want (governed
    by rescope_cap instead), but starting over on a new subject counts the
    same regardless of which button got you there."""
    return body.type == "rescope_request" and body.different_topic


@app.post("/runs/{run_id}/respond")
def respond(run_id: str, body: RespondBody, request: Request) -> Dict[str, Any]:
    cfg = {"configurable": {"thread_id": run_id}}
    settings = get_settings()
    # Check the job record before the checkpointer: a run that's still
    # working hasn't necessarily written state yet, and reading first would
    # 404 a run that plainly exists.
    running = _jobs.get(run_id)
    if running and running["status"] == "running":
        return _job_view(run_id, running, _maps_counter(request, settings))
    snap = _ctx["graph"].get_state(cfg)
    if not snap.created_at:
        raise HTTPException(404, f"unknown run {run_id}")
    if _is_fresh_map_request(body) and not _is_owner(request, settings):
        try:
            check_and_record(client_ip(request), settings)
        except RateLimitExceeded as exc:
            raise HTTPException(
                429,
                f"Daily demo limit reached ({exc.scope}: {exc.limit}/day). Try again tomorrow.",
            )
    job = _start_job(run_id, Command(resume=body.model_dump()), cfg)
    return _job_view(run_id, job, _maps_counter(request, settings))


@app.get("/runs/{run_id}")
def get_run(run_id: str, request: Request) -> Dict[str, Any]:
    """What the client polls while a job runs."""
    job = _jobs.get(run_id)
    if job is not None:
        return _job_view(run_id, job, _maps_counter(request, get_settings()))

    # No job record: this process didn't start the run, or restarted since.
    # The checkpointer may still hold the state, so answer from that rather
    # than claiming the run never existed.
    cfg = {"configurable": {"thread_id": run_id}}
    snap = _ctx["graph"].get_state(cfg)
    if not snap.created_at:
        raise HTTPException(404, f"unknown run {run_id}")
    values = snap.values
    final = values.get("final_output")
    return {
        "run_id": run_id,
        "status": "complete" if final else "interrupted",
        "phase": None,
        "maps": _maps_counter(request, get_settings()),
        "final_output": final,
        "metrics": values.get("metrics"),
        "topic": values.get("topic"),
        "proposal": values.get("proposal"),
        "confirmed_scope": values.get("confirmed_scope"),
        "next": list(snap.next),
    }
