"""Daily run cap for the public deployment: a stranger with the link can spend
real Anthropic + Exa credits, so a new run (one "map") is gated by two counts
-- per-IP and a global backstop -- before the graph is ever invoked. Off by
default (both limits None) so local dev and tests are unaffected; the public
deploy sets both via env vars (see docs/DEPLOY.md).

In-memory, not Postgres-backed: the public demo is a single Railway instance,
so a plain dict is enough, and it's honest about resetting on redeploy/restart
rather than pretending to a durability guarantee this doesn't need.
"""
from __future__ import annotations

import threading
from datetime import date
from typing import Dict, Optional, Tuple

from fastapi import Request

from .config import Settings

_GLOBAL_KEY = "_global"
_lock = threading.Lock()
_counts: Dict[Tuple[str, str], int] = {}  # (iso_date, ip_or_global) -> count


class RateLimitExceeded(Exception):
    def __init__(self, scope: str, limit: int):
        self.scope = scope  # "per-IP" | "global"
        self.limit = limit
        super().__init__(f"{scope} daily run limit ({limit}) reached")


def client_ip(request: Request) -> str:
    """Real client IP behind Railway's proxy: X-Forwarded-For's first hop,
    falling back to the direct peer for local/dev where there's no proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _prune_other_days(today: str) -> None:
    stale = [k for k in _counts if k[0] != today]
    for k in stale:
        del _counts[k]


def check_and_record(ip: str, settings: Settings) -> None:
    """Raise RateLimitExceeded if today's cap is already hit; otherwise record
    this run against both counters. Call once per new run, before it starts."""
    if settings.daily_run_limit_per_ip is None and settings.daily_run_limit_global is None:
        return

    today = date.today().isoformat()
    with _lock:
        _prune_other_days(today)

        global_count = _counts.get((today, _GLOBAL_KEY), 0)
        if settings.daily_run_limit_global is not None and global_count >= settings.daily_run_limit_global:
            raise RateLimitExceeded("global", settings.daily_run_limit_global)

        ip_count = _counts.get((today, ip), 0)
        if settings.daily_run_limit_per_ip is not None and ip_count >= settings.daily_run_limit_per_ip:
            raise RateLimitExceeded("per-IP", settings.daily_run_limit_per_ip)

        _counts[(today, _GLOBAL_KEY)] = global_count + 1
        _counts[(today, ip)] = ip_count + 1
