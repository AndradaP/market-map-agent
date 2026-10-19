"""Checkpointer selection.

The checkpointer is what makes the confirm/edit `interrupt()` durable: when a run
suspends to wait on the user, its full in-progress state is written to Postgres,
so a different process can resume it. Falls back to in-memory for local/e2e runs.
"""
from __future__ import annotations

import logging

from .config import Settings

log = logging.getLogger(__name__)


class Checkpointer:
    """Holds the saver plus whatever needs closing on shutdown."""

    def __init__(self, saver, pool=None, degraded: str = ""):
        self.saver = saver
        self._pool = pool
        # Empty when the configured backend is the one actually in use.
        # Non-empty means Postgres was configured but unreachable, and this
        # process is running on in-memory state instead.
        self.degraded = degraded

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()


def _memory(degraded: str = "") -> Checkpointer:
    from langgraph.checkpoint.memory import MemorySaver

    return Checkpointer(MemorySaver(), degraded=degraded)


def build_checkpointer(settings: Settings) -> Checkpointer:
    if settings.database_url:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        from langgraph.checkpoint.postgres import PostgresSaver

        # PostgresSaver.from_conn_string() opens ONE bare connection and holds
        # it for the process's whole life -- if Supabase's pooler (or just
        # network flakiness) drops it from being idle, every run after that
        # hard-fails with "the connection is closed" until the process
        # restarts (found live, running this backend against a real Supabase
        # instance). PostgresSaver natively accepts a ConnectionPool instead
        # of a bare Connection (see langgraph.checkpoint.postgres._internal);
        # a pool transparently replaces a dead connection with a fresh one
        # rather than holding one connection forever.
        pool = None
        try:
            pool = ConnectionPool(
                conninfo=settings.database_url.get_secret_value(),
                min_size=1,
                max_size=5,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                    "row_factory": dict_row,
                    # Fail fast per attempt. The default lets an unroutable
                    # host hang until the pool's own timeout, turning a bad
                    # connection string into a minutes-long startup stall.
                    "connect_timeout": 5,
                },
                check=ConnectionPool.check_connection,
                timeout=8,
                open=True,
            )
            saver = PostgresSaver(pool)
            saver.setup()  # idempotent: creates checkpoint tables if absent
            return Checkpointer(saver, pool=pool)
        except Exception as exc:  # noqa: BLE001
            # An unreachable database must not take the whole service down.
            # It did exactly that in production: a Supabase *direct*
            # connection string resolves to an IPv6 address, Railway
            # containers have no IPv6 route, so setup() timed out, the
            # FastAPI lifespan hook raised, and the container crash-looped
            # with every endpoint returning 502 -- including the ones that
            # never touch the database. Durable runs are worth having, but
            # they are not worth the entire app.
            if pool is not None:
                try:
                    pool.close()
                except Exception:  # noqa: BLE001
                    pass
            reason = f"{type(exc).__name__}: {exc}"
            log.error(
                "Postgres checkpointer unavailable, falling back to in-memory. "
                "Runs will not survive a restart. Cause: %s",
                reason,
            )
            return _memory(degraded=reason)

    return _memory()
