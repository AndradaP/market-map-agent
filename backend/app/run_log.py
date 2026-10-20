"""The run log (memory): one row per completed run, written once at the end.

This is the intentional eval record, separate in purpose from the LangGraph
checkpointer even though both live in the same Supabase Postgres. Offline it
appends JSON lines to backend/out/runs.local.jsonl.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from .config import Settings
from .utils import now_iso

log = logging.getLogger(__name__)

_LOCAL_LOG = Path(__file__).resolve().parents[1] / "out" / "runs.local.jsonl"


def build_run_record(state: dict, final_output: dict, metrics: dict) -> Dict[str, Any]:
    scope = state.get("confirmed_scope", {}) or {}
    return {
        "run_id": state.get("run_id"),
        "timestamp": now_iso(),
        "topic": state.get("topic"),
        "confirmed_scope_summary": {
            "layers": scope.get("layers", []),
            "zoom_level": scope.get("zoom_level"),
            "in_scope": scope.get("in_scope", []),
            "excluded_adjacent": scope.get("excluded_adjacent", []),
        },
        "num_layers": metrics.get("layers", 0),
        "companies_found": metrics.get("companies_found", 0),
        "companies_verified": metrics.get("companies_verified", 0),
        "companies_under_corroborated": metrics.get("companies_under_corroborated", 0),
        "rejected_failed_corroboration": metrics.get("rejected_failed_corroboration", 0),
        "rejected_failed_category_fit": metrics.get("rejected_failed_category_fit", 0),
        "rejected_failed_existence": metrics.get("rejected_failed_existence", 0),
        "layers_reformulated": metrics.get("layers_reformulated", 0),
        "layers_over_cap": metrics.get("layers_over_cap", 0),
        "rescope_count": metrics.get("rescope_count", 0),
        "back_edge_fired": metrics.get("rescope_count", 0) > 0,
        "cap_hit": metrics.get("cap_hit", False),
        "direct_edit_takeover": metrics.get("cap_hit", False),
        # Cost / tokens / latency: filled from LangSmith when tracing is on.
        # In stub mode these stay null/0 by design.
        "cost_usd": metrics.get("cost_usd"),
        "total_tokens": metrics.get("total_tokens"),
        "latency_s": metrics.get("latency_s"),
        "warnings": final_output.get("warnings", []),
    }


_INSERT_SQL = """
insert into market_map_runs (
  run_id, topic, confirmed_scope_summary, num_layers,
  companies_found, companies_verified, companies_under_corroborated,
  rejected_failed_corroboration, rejected_failed_category_fit, rejected_failed_existence,
  layers_reformulated, layers_over_cap,
  rescope_count, cap_hit, direct_edit_takeover,
  cost_usd, total_tokens, latency_s, warnings, created_at
) values (
  %(run_id)s, %(topic)s, %(confirmed_scope_summary)s, %(num_layers)s,
  %(companies_found)s, %(companies_verified)s, %(companies_under_corroborated)s,
  %(rejected_failed_corroboration)s, %(rejected_failed_category_fit)s, %(rejected_failed_existence)s,
  %(layers_reformulated)s, %(layers_over_cap)s,
  %(rescope_count)s, %(cap_hit)s, %(direct_edit_takeover)s,
  %(cost_usd)s, %(total_tokens)s, %(latency_s)s, %(warnings)s, %(timestamp)s
)
on conflict (run_id) do nothing;
"""


def _write_postgres(record: Dict[str, Any], settings: Settings) -> None:
    import psycopg
    from psycopg.types.json import Jsonb

    payload = dict(record)
    payload["confirmed_scope_summary"] = Jsonb(payload["confirmed_scope_summary"])
    payload["warnings"] = Jsonb(payload["warnings"])
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        conn.execute(_INSERT_SQL, payload)
        conn.commit()


def _write_local(record: Dict[str, Any]) -> None:
    _LOCAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _LOCAL_LOG.open("a") as fh:
        fh.write(json.dumps(record) + "\n")


def write_run_log(record: Dict[str, Any], settings: Settings) -> Dict[str, Any]:
    """Best effort, always. This is an eval record, not the deliverable.

    It used to raise, and raising here is uniquely expensive because this is
    the LAST thing a run does: a complete map, minutes of research and real
    API spend, was thrown away in production because this row couldn't be
    written (the database was unreachable over IPv6 from the host). The map
    is the product; the log row is bookkeeping. Never trade one for the
    other -- registry.py already worked this way, this didn't.
    """
    # Stub mode always uses the local file, regardless of DATABASE_URL --
    # found live via a failing test: a real DATABASE_URL sitting in a dev's
    # .env meant every offline/stub run (including the whole test suite)
    # silently wrote rows into the REAL production market_map_runs table.
    if settings.database_url and not settings.stubs_enabled:
        try:
            _write_postgres(record, settings)
            return record
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "run-log Postgres write failed, falling back to the local file: %s", exc
            )
    try:
        _write_local(record)
    except Exception as exc:  # noqa: BLE001 -- even losing the record beats losing the run
        log.warning("run-log local write failed, continuing without it: %s", exc)
    return record
