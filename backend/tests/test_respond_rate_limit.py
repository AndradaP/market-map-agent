"""A 'different topic' rescope re-runs Recon + Propose from scratch -- the
same cost profile as POST /runs -- so it has to share the same daily cap.
Found live: it didn't, which was a free way around the 2-map/day guardrail
(narrow the same topic all you want on rescope_cap, but hop to a brand new
topic via the checkbox instead of the "start a new market map" button and
it cost nothing). A same-topic rescope must stay completely free either way
-- that one's governed only by rescope_cap, a separate, smaller guardrail."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import importlib

import pytest
from fastapi.testclient import TestClient

from backend.app import config, rate_limit

TOPIC = "AI observability"
DIFFERENT_TOPIC_RESCOPE = {
    "type": "rescope_request",
    "notes": "actually this is a totally different topic, please start over",
    "different_topic": True,
}
SAME_TOPIC_RESCOPE = {
    "type": "rescope_request",
    "notes": "split storage from instrumentation, they're too broad together",
    "different_topic": False,
}


@pytest.fixture
def app_client(monkeypatch):
    monkeypatch.setenv("USE_STUBS", "true")
    monkeypatch.setenv("DAILY_RUN_LIMIT_PER_IP", "2")
    monkeypatch.delenv("DAILY_RUN_LIMIT_GLOBAL", raising=False)
    monkeypatch.delenv("RATE_LIMIT_BYPASS_TOKEN", raising=False)
    # .env's real DATABASE_URL/LANGSMITH_API_KEY would otherwise leak in here
    # (pydantic-settings reads .env regardless of which vars this test sets)
    # and the lifespan would try to open a real Postgres pool against an
    # unreachable host, hanging ~30s per attempt.
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("LANGSMITH_API_KEY", "")
    config.get_settings.cache_clear()
    monkeypatch.setattr(rate_limit, "_counts", {})

    from backend.app import main as main_module

    importlib.reload(main_module)
    with TestClient(main_module.app) as client:
        yield client
    config.get_settings.cache_clear()


def test_different_topic_rescope_counts_against_the_daily_cap(app_client):
    r1 = app_client.post("/runs", json={"topic": TOPIC})
    assert r1.status_code == 200
    run_id = r1.json()["run_id"]

    # 2nd "map" via a different-topic rescope on the SAME run -- allowed,
    # this is the 2nd of 2 slots for today.
    r2 = app_client.post(f"/runs/{run_id}/respond", json=DIFFERENT_TOPIC_RESCOPE)
    assert r2.status_code == 200

    # A 3rd fresh map, regardless of which button it comes from, is refused.
    r3 = app_client.post(f"/runs/{run_id}/respond", json=DIFFERENT_TOPIC_RESCOPE)
    assert r3.status_code == 429


def test_same_topic_rescope_never_counts_against_the_daily_cap(app_client):
    r1 = app_client.post("/runs", json={"topic": TOPIC})
    run_id = r1.json()["run_id"]

    # Spend the other daily slot on an actual second run ...
    r2 = app_client.post("/runs", json={"topic": "geothermal"})
    assert r2.status_code == 200

    # ... the cap is now fully spent, but narrowing the FIRST run's own
    # topic is a same-topic rescope and must still go through freely.
    r3 = app_client.post(f"/runs/{run_id}/respond", json=SAME_TOPIC_RESCOPE)
    assert r3.status_code == 200


def test_owner_bypass_still_works_on_a_different_topic_rescope(monkeypatch):
    monkeypatch.setenv("USE_STUBS", "true")
    monkeypatch.setenv("DAILY_RUN_LIMIT_PER_IP", "1")
    monkeypatch.setenv("RATE_LIMIT_BYPASS_TOKEN", "secret123")
    monkeypatch.delenv("DAILY_RUN_LIMIT_GLOBAL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("LANGSMITH_API_KEY", "")
    config.get_settings.cache_clear()
    monkeypatch.setattr(rate_limit, "_counts", {})

    from backend.app import main as main_module

    importlib.reload(main_module)
    headers = {"X-Owner-Token": "secret123"}
    with TestClient(main_module.app) as client:
        r1 = client.post("/runs", json={"topic": TOPIC}, headers=headers)
        run_id = r1.json()["run_id"]
        # Cap is 1/day, already spent above by a non-owner accounting... but
        # this request carried the owner header, so it was never recorded.
        r2 = client.post(
            f"/runs/{run_id}/respond", json=DIFFERENT_TOPIC_RESCOPE, headers=headers
        )
        assert r2.status_code == 200
        r3 = client.post(
            f"/runs/{run_id}/respond", json=DIFFERENT_TOPIC_RESCOPE, headers=headers
        )
        assert r3.status_code == 200
    config.get_settings.cache_clear()
