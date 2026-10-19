"""build_checkpointer: PostgresSaver must be given a ConnectionPool, not a bare
connection. A live run found `.from_conn_string()` (one bare connection held
for the process's whole life) fails hard with "the connection is closed" once
Supabase's pooler (or just network flakiness) drops it -- every run after
that 500s until the process restarts. A pool transparently replaces a dead
connection instead."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.checkpointer import build_checkpointer
from backend.app.config import Settings


def test_no_database_url_falls_back_to_memory_saver():
    from langgraph.checkpoint.memory import MemorySaver

    cp = build_checkpointer(Settings(use_stubs=False, database_url=""))
    assert isinstance(cp.saver, MemorySaver)
    cp.close()  # must not raise with no pool to close


def test_database_url_builds_postgres_saver_on_a_pool(monkeypatch):
    import psycopg_pool
    import langgraph.checkpoint.postgres as pg_checkpoint

    created = {}

    class FakePool:
        check_connection = staticmethod(lambda conn: None)

        def __init__(self, *, conninfo, **kw):
            created["conninfo"] = conninfo
            created["kwargs"] = kw
            self.closed = False

        def close(self):
            self.closed = True

    class FakeSaver:
        def __init__(self, conn):
            created["conn_passed_to_saver"] = conn

        def setup(self):
            created["setup_called"] = True

    monkeypatch.setattr(psycopg_pool, "ConnectionPool", FakePool)
    monkeypatch.setattr(pg_checkpoint, "PostgresSaver", FakeSaver)

    cp = build_checkpointer(Settings(use_stubs=False, database_url="postgresql://u:p@host/db"))

    assert isinstance(cp.saver, FakeSaver)
    assert created["setup_called"] is True
    # the saver must be handed the POOL itself, not a one-off connection --
    # that's the whole point of the fix
    assert created["conn_passed_to_saver"] is cp._pool
    assert isinstance(cp._pool, FakePool)
    assert "postgresql://u:p@host/db" == created["conninfo"]

    cp.close()
    assert cp._pool.closed is True
    assert cp.degraded == ""


def test_unreachable_database_degrades_instead_of_killing_the_app(monkeypatch):
    """Found in production: a Supabase *direct* connection string resolves to
    IPv6, Railway has no IPv6 route, setup() timed out, the lifespan hook
    raised, and the container crash-looped -- every endpoint 502, including
    the ones that never touch the database."""
    import psycopg_pool
    import langgraph.checkpoint.postgres as pg_checkpoint
    from langgraph.checkpoint.memory import MemorySaver

    closed = {}

    class DeadPool:
        check_connection = staticmethod(lambda conn: None)

        def __init__(self, **kw):
            closed["opened"] = True

        def close(self):
            closed["closed"] = True

    class TimingOutSaver:
        def __init__(self, conn):
            pass

        def setup(self):
            raise TimeoutError("couldn't get a connection after 30.00 sec")

    monkeypatch.setattr(psycopg_pool, "ConnectionPool", DeadPool)
    monkeypatch.setattr(pg_checkpoint, "PostgresSaver", TimingOutSaver)

    cp = build_checkpointer(Settings(use_stubs=False, database_url="postgresql://u:p@host/db"))

    assert isinstance(cp.saver, MemorySaver), "app must still start, on memory"
    assert "TimeoutError" in cp.degraded, "and must say why, not fail silently"
    assert closed.get("closed") is True, "the half-open pool must be released"
    cp.close()


def test_pool_is_configured_to_fail_fast(monkeypatch):
    # Without a short connect_timeout an unroutable host stalls startup for
    # minutes before the fallback can kick in.
    import psycopg_pool
    import langgraph.checkpoint.postgres as pg_checkpoint

    seen = {}

    class FakePool:
        check_connection = staticmethod(lambda conn: None)

        def __init__(self, **kw):
            seen.update(kw)

        def close(self):
            pass

    monkeypatch.setattr(psycopg_pool, "ConnectionPool", FakePool)
    monkeypatch.setattr(pg_checkpoint, "PostgresSaver", lambda conn: type("S", (), {"setup": lambda self: None})())

    build_checkpointer(Settings(use_stubs=False, database_url="postgresql://u:p@host/db"))

    assert seen["kwargs"]["connect_timeout"] == 5
    assert seen["timeout"] == 8
