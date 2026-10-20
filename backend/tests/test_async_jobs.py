"""Work runs in the background and the client polls for it.

Measured against the deployed backend: Railway's edge proxy kills any single
HTTP request at exactly 300s (a research pass 502'd at 300.3s), and a real
research pass routinely runs longer than that. Holding the connection could
never have worked for a real map no matter how patient the client was, and
when it died the user lost a run the server had already paid for.
"""
from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from fastapi.testclient import TestClient

from backend.app import config, rate_limit

TOPIC = "AI observability"
CONFIRM = {"type": "none", "notes": "", "different_topic": False, "edited_scope": None}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("USE_STUBS", "true")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("LANGSMITH_API_KEY", "")
    monkeypatch.delenv("DAILY_RUN_LIMIT_PER_IP", raising=False)
    monkeypatch.delenv("DAILY_RUN_LIMIT_GLOBAL", raising=False)
    config.get_settings.cache_clear()
    monkeypatch.setattr(rate_limit, "_counts", {})

    from backend.app import main as main_module

    importlib.reload(main_module)
    with TestClient(main_module.app) as c:
        yield c
    config.get_settings.cache_clear()


def _await(client, run_id, want, timeout=20):
    """Poll the way the browser does."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/runs/{run_id}").json()
        if body["status"] == want:
            return body
        if body["status"] == "error":
            raise AssertionError(f"run failed: {body.get('error')}")
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {want}")


def test_post_returns_immediately_instead_of_holding_the_connection(client):
    t0 = time.time()
    body = client.post("/runs", json={"topic": TOPIC}).json()
    assert time.time() - t0 < 2, "POST must not block on the work"
    assert body["status"] == "running"
    assert body["run_id"]


def test_polling_carries_a_run_through_to_the_proposal(client):
    run_id = client.post("/runs", json={"topic": TOPIC}).json()["run_id"]
    body = _await(client, run_id, "awaiting_confirmation")
    assert body["review"]["proposal"]["layers"]


def test_polling_carries_a_confirmed_run_through_to_a_finished_map(client):
    run_id = client.post("/runs", json={"topic": TOPIC}).json()["run_id"]
    _await(client, run_id, "awaiting_confirmation")

    client.post(f"/runs/{run_id}/respond", json=CONFIRM)
    body = _await(client, run_id, "complete")

    assert body["final_output"]["topic"] == TOPIC
    assert body["final_output"]["layers"]


def test_a_second_post_does_not_fork_a_run_already_in_flight(client):
    """A double-click must not start the expensive work twice."""
    run_id = client.post("/runs", json={"topic": TOPIC}).json()["run_id"]
    _await(client, run_id, "awaiting_confirmation")

    first = client.post(f"/runs/{run_id}/respond", json=CONFIRM).json()
    second = client.post(f"/runs/{run_id}/respond", json=CONFIRM).json()

    assert first["run_id"] == second["run_id"] == run_id
    assert second["status"] in {"running", "complete"}
    _await(client, run_id, "complete")


def test_unknown_run_still_404s(client):
    assert client.get("/runs/nope").status_code == 404


def test_phase_names_a_real_graph_node(client):
    """The client shows the phase as prose, so it has to be a node name the
    frontend's PHASES map knows, not an invented label."""
    known = {"recon", "propose", "confirm", "execute", "verify", "synthesize"}
    run_id = client.post("/runs", json={"topic": TOPIC}).json()["run_id"]
    seen = set()
    deadline = time.time() + 20
    while time.time() < deadline:
        body = client.get(f"/runs/{run_id}").json()
        if body.get("phase"):
            seen.add(body["phase"])
        if body["status"] != "running":
            break
        time.sleep(0.02)
    assert seen <= known, f"unknown phase(s): {seen - known}"
