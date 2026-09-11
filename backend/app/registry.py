"""Persistent, cross-run company identity.

Each layer's search->extract->corroborate pipeline runs in isolation per run
(see nodes/execute.py) -- without a shared record, the same real company gets
re-litigated from scratch by search luck every time it comes up under a
different topic or layer (seen live: Nscale scored 4 independent sources
under one topic, 1 under an adjacent one -- same real company, same day).

This module gives every company a canonical identity keyed by domain, and
accumulates the independent sources ever found for it across every run and
topic. It's meant to grow monotonically, not be cleared between runs -- the
whole point is that the tool gets more confident about a real company's
standing the more it's encountered, instead of starting from zero every time.

Falls back to a local JSON file when no DATABASE_URL is set, same pattern as
run_log.py. A registry hiccup degrades to "no memory" (this run's freshly
found sources only) rather than sinking the pipeline -- it's a bonus signal
layered on top of the real corroboration gate, never itself load-bearing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

from .config import Settings
from .utils import host_of, now_iso

_LOCAL_REGISTRY = Path(__file__).resolve().parents[1] / "out" / "company_registry.local.json"


def _load_local() -> dict:
    if _LOCAL_REGISTRY.exists():
        return json.loads(_LOCAL_REGISTRY.read_text())
    return {}


def _save_local(data: dict) -> None:
    _LOCAL_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    _LOCAL_REGISTRY.write_text(json.dumps(data, indent=2))


def _dedupe_sources(sources: List[dict]) -> List[dict]:
    seen: dict = {}
    for s in sources:
        u = s.get("url") if isinstance(s, dict) else str(s)
        if u and u not in seen:
            seen[u] = {"url": u, "title": s.get("title", "") if isinstance(s, dict) else ""}
    return list(seen.values())


def merge_and_store(
    *, name: str, url: str, new_sources: List[dict], topic: str, settings: Settings
) -> Tuple[str, List[dict]]:
    """Merge this run's freshly-found sources for one company with whatever
    the registry already knows about it (keyed by canonical host), persist
    the union, and return (best_known_name, merged_sources) to score against.

    A no-op pass-through in stub mode -- tests use hand-authored fixtures with
    exact expected outcomes; letting registry state leak across test runs
    would make them order-dependent and non-deterministic.
    """
    if settings.stubs_enabled:
        return name, new_sources

    host = host_of(url)
    if not host:
        return name, new_sources

    try:
        if settings.database_url:
            return _merge_postgres(host, name, new_sources, topic, settings)
        return _merge_local(host, name, new_sources, topic)
    except Exception:  # noqa: BLE001 -- memory is a bonus signal, never load-bearing
        return name, new_sources


def _merge_local(host: str, name: str, new_sources: List[dict], topic: str) -> Tuple[str, List[dict]]:
    data = _load_local()
    row = data.get(host, {"canonical_name": name, "sources": [], "topics_seen": [], "times_seen": 0})
    canonical_name = max([row["canonical_name"], name], key=len)
    merged = _dedupe_sources(row["sources"] + list(new_sources))
    topics_seen = sorted(set(row["topics_seen"]) | {topic})
    data[host] = {
        "canonical_name": canonical_name,
        "sources": merged,
        "topics_seen": topics_seen,
        "times_seen": row["times_seen"] + 1,
        "last_seen_at": now_iso(),
    }
    _save_local(data)
    return canonical_name, merged


def _merge_postgres(
    host: str, name: str, new_sources: List[dict], topic: str, settings: Settings
) -> Tuple[str, List[dict]]:
    import psycopg
    from psycopg.types.json import Jsonb

    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        row = conn.execute(
            "select canonical_name, sources, topics_seen from company_registry "
            "where canonical_host = %s",
            (host,),
        ).fetchone()
        if row:
            canonical_name = max([row[0], name], key=len)
            merged = _dedupe_sources(list(row[1]) + list(new_sources))
            topics_seen = sorted(set(row[2]) | {topic})
            conn.execute(
                "update company_registry set canonical_name = %s, sources = %s, "
                "topics_seen = %s, times_seen = times_seen + 1, last_seen_at = now() "
                "where canonical_host = %s",
                (canonical_name, Jsonb(merged), topics_seen, host),
            )
        else:
            canonical_name = name
            merged = _dedupe_sources(new_sources)
            conn.execute(
                "insert into company_registry (canonical_host, canonical_name, sources, topics_seen) "
                "values (%s, %s, %s, %s)",
                (host, canonical_name, Jsonb(merged), [topic]),
            )
        conn.commit()
    return canonical_name, merged
