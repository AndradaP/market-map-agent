"""FastAPI surface for the web form. Thin wrapper over the LangGraph app that
supports the pause/resume gate.

    POST /runs                 {topic}                    -> proposal (interrupt)
    POST /runs/{id}/respond    {type, notes, ...}         -> next proposal | final map
    GET  /runs/{id}                                       -> current state snapshot
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from langgraph.types import Command
from pydantic import BaseModel

from .checkpointer import build_checkpointer
from .config import get_settings
from .graph import build_graph
from .rate_limit import RateLimitExceeded, check_and_record, client_ip
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
        "checkpointer": settings.checkpointer_backend,
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
    normalize: bool = False  # direct_edit: tidy user-added layer names/order (not a rescope)


def _interrupt_payload(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    intr = result.get("__interrupt__")
    if not intr:
        return None
    first = intr[0]
    return getattr(first, "value", first)


def _shape(result: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    payload = _interrupt_payload(result)
    if payload is not None:
        return {"run_id": run_id, "status": "awaiting_confirmation", "review": payload}
    return {
        "run_id": run_id,
        "status": "complete",
        "final_output": result.get("final_output"),
        "metrics": result.get("metrics"),
    }


@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    return {"ok": True, **_ctx.get("meta", {})}


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
    result = _ctx["graph"].invoke({"topic": body.topic, "run_id": run_id}, cfg)
    return _shape(result, run_id)


@app.post("/runs/{run_id}/respond")
def respond(run_id: str, body: RespondBody) -> Dict[str, Any]:
    cfg = {"configurable": {"thread_id": run_id}}
    snap = _ctx["graph"].get_state(cfg)
    if not snap.created_at:
        raise HTTPException(404, f"unknown run {run_id}")
    result = _ctx["graph"].invoke(Command(resume=body.model_dump()), cfg)
    return _shape(result, run_id)


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> Dict[str, Any]:
    cfg = {"configurable": {"thread_id": run_id}}
    snap = _ctx["graph"].get_state(cfg)
    if not snap.created_at:
        raise HTTPException(404, f"unknown run {run_id}")
    values = snap.values
    return {
        "run_id": run_id,
        "next": list(snap.next),
        "topic": values.get("topic"),
        "proposal": values.get("proposal"),
        "confirmed_scope": values.get("confirmed_scope"),
        "rescope_count": values.get("rescope_count", 0),
        "cap_hit": values.get("cap_hit", False),
        "final_output": values.get("final_output"),
        "metrics": values.get("metrics"),
    }
