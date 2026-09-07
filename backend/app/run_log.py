"""The run log (memory): one row per completed run, written once at the end.

This is the intentional eval record, separate in purpose from the LangGraph
checkpointer even though both live in the same Supabase Postgres. Offline it
appends JSON lines to backend/out/runs.local.jsonl.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .config import Settings
from .utils import now_iso

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


def write_run_log(record: Dict[str, Any], settings: Settings) -> Dict[str, Any]:
    if settings.database_url:
        import psycopg
        from psycopg.types.json import Jsonb

        payload = dict(record)
        payload["confirmed_scope_summary"] = Jsonb(payload["confirmed_scope_summary"])
        payload["warnings"] = Jsonb(payload["warnings"])
        with psycopg.connect(settings.database_url) as conn:
            conn.execute(_INSERT_SQL, payload)
            conn.commit()
        return record

    _LOCAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _LOCAL_LOG.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    return record
