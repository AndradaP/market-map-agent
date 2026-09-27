"""Found live: write_run_log gated only on `settings.database_url`, with no
stub-mode check -- registry.py already gates its own Postgres path on
stubs_enabled first, this one never did. Consequence: any offline/stub run
(the whole test suite included) with a real DATABASE_URL sitting in a dev's
.env silently wrote rows into the REAL production market_map_runs table."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app import run_log
from backend.app.config import Settings

REAL_LOOKING_DB_URL = "postgresql://user:pass@db.example.invalid:5432/postgres"


def test_stub_mode_never_touches_postgres_even_with_a_real_looking_url(monkeypatch, tmp_path):
    monkeypatch.setattr(run_log, "_LOCAL_LOG", tmp_path / "runs.local.jsonl")

    def _boom(*a, **kw):
        raise AssertionError("stub mode must never call psycopg.connect")

    monkeypatch.setattr("psycopg.connect", _boom, raising=False)

    settings = Settings(use_stubs=True, database_url=REAL_LOOKING_DB_URL)
    record = {"run_id": "t", "topic": "x"}
    out = run_log.write_run_log(record, settings)

    assert out == record
    assert (tmp_path / "runs.local.jsonl").exists()


def test_real_mode_with_a_database_url_does_use_postgres(monkeypatch, tmp_path):
    monkeypatch.setattr(run_log, "_LOCAL_LOG", tmp_path / "runs.local.jsonl")
    calls = []

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, *a, **kw):
            calls.append(a)

        def commit(self):
            pass

    monkeypatch.setattr("psycopg.connect", lambda *a, **kw: _FakeConn(), raising=False)

    settings = Settings(
        use_stubs=False,
        anthropic_api_key="x",
        exa_api_key="y",
        database_url=REAL_LOOKING_DB_URL,
    )
    record = {
        "run_id": "t",
        "topic": "x",
        "confirmed_scope_summary": {},
        "warnings": [],
    }
    run_log.write_run_log(record, settings)

    assert calls, "expected a real Postgres call when not in stub mode"
    assert not (tmp_path / "runs.local.jsonl").exists()
