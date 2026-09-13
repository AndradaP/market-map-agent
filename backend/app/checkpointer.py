"""Checkpointer selection.

The checkpointer is what makes the confirm/edit `interrupt()` durable: when a run
suspends to wait on the user, its full in-progress state is written to Postgres,
so a different process can resume it. Falls back to in-memory for local/e2e runs.
"""
from __future__ import annotations

from .config import Settings


class Checkpointer:
    """Holds the saver plus whatever needs closing on shutdown."""

    def __init__(self, saver, pool=None):
        self.saver = saver
        self._pool = pool

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()


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
        pool = ConnectionPool(
            conninfo=settings.database_url.get_secret_value(),
            min_size=1,
            max_size=5,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            check=ConnectionPool.check_connection,
            open=True,
        )
        saver = PostgresSaver(pool)
        saver.setup()  # idempotent: creates checkpoint tables if absent
        return Checkpointer(saver, pool=pool)

    from langgraph.checkpoint.memory import MemorySaver

    return Checkpointer(MemorySaver())
