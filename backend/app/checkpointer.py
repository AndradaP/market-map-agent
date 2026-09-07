"""Checkpointer selection.

The checkpointer is what makes the confirm/edit `interrupt()` durable: when a run
suspends to wait on the user, its full in-progress state is written to Postgres,
so a different process can resume it. Falls back to in-memory for local/e2e runs.
"""
from __future__ import annotations

from typing import Optional, Tuple

from .config import Settings


class Checkpointer:
    """Holds the saver plus the context manager that must stay open for its life."""

    def __init__(self, saver, cm=None):
        self.saver = saver
        self._cm = cm

    def close(self) -> None:
        if self._cm is not None:
            self._cm.__exit__(None, None, None)


def build_checkpointer(settings: Settings) -> Checkpointer:
    if settings.database_url:
        from langgraph.checkpoint.postgres import PostgresSaver

        cm = PostgresSaver.from_conn_string(settings.database_url)
        saver = cm.__enter__()
        saver.setup()  # idempotent: creates checkpoint tables if absent
        return Checkpointer(saver, cm)

    from langgraph.checkpoint.memory import MemorySaver

    return Checkpointer(MemorySaver())
