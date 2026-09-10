"""Node 6 — Synthesize. Assemble the final map + write the run log.

Structured data first. Honest about empties:
  - a layer with no usable results stays in the map with status ``no_results``
  - verified-but-under-corroborated companies go to ``final_output.needs_review``,
    not the main list, so the human can rescue them
  - a layer that overflowed the hard cap gets a "too broad — consider splitting"
    warning instead of a silent truncation
"""
from __future__ import annotations

from typing import Any, Dict, List

from .. import llm, run_log
from ..config import get_settings
from ..state import Company, MarketMapState
from ..utils import host_of, now_iso

_STATUS_RANK = {"corroborated": 0, "under_corroborated": 1, "uncorroborated": 2}


def _dedupe_across_layers(research: Dict[str, List[Company]]) -> Dict[str, List[Company]]:
    """Each layer's search->extract->corroborate pipeline runs in isolation
    (see execute_node), so the same real company routinely gets extracted
    independently by more than one layer -- seen live, ~15% of a run's entries
    could be the same handful of companies repeated 2-3x. Canonicalize by host
    (this also absorbs cosmetic URL differences like www./trailing slash that
    were otherwise causing the SAME url to pass existence in one layer and
    transiently fail it in another) and keep only the single best-status
    instance across the whole run.
    """
    best_by_host: Dict[str, tuple] = {}  # host -> (rank, (layer, index))
    for layer, cands in research.items():
        for idx, c in enumerate(cands):
            host = host_of(c.get("url", ""))
            if not host:
                continue
            corrob = c.get("corroboration", {})
            rank = (
                _STATUS_RANK.get(corrob.get("status"), 2),
                -len(corrob.get("independent_hosts", [])),
                -corrob.get("score", 0.0),
            )
            key = (layer, idx)
            cur = best_by_host.get(host)
            if cur is None or rank < cur[0]:
                best_by_host[host] = (rank, key)

    winners = {key for _, key in best_by_host.values()}
    return {
        layer: [
            c for idx, c in enumerate(cands)
            if not host_of(c.get("url", "")) or (layer, idx) in winners
        ]
        for layer, cands in research.items()
    }


def synthesize_node(state: MarketMapState) -> dict:
    settings = get_settings()
    scope = state["confirmed_scope"]
    defs: Dict[str, str] = scope.get("layer_definitions", {})
    adjacent: List[str] = scope.get("excluded_adjacent", [])
    research: Dict[str, List[Company]] = _dedupe_across_layers(state.get("layer_research", {}))
    layer_meta: Dict[str, Any] = state.get("layer_meta", {})
    soft, hard = settings.layer_company_soft_target, settings.layer_company_hard_cap

    layers_out: List[dict] = []
    rejected: List[Company] = []
    needs_review: List[Company] = []
    warnings: List[str] = []
    n_found = n_verified = n_under = 0
    rej_corr = rej_fit = rej_exist = 0
    n_reformulated = n_over_cap = 0

    for layer in scope.get("layers", []):
        cands = research.get(layer, [])
        meta = layer_meta.get(layer, {})
        n_found += meta.get("raw_count", len(cands))

        verified = [c for c in cands if c.get("verified")]
        strong = [c for c in verified if c.get("corroboration", {}).get("status") == "corroborated"]
        weak = [c for c in verified if c.get("corroboration", {}).get("status") == "under_corroborated"]
        n_verified += len(strong)
        n_under += len(weak)

        for c in weak:
            needs_review.append({**c, "layer": layer})

        for c in cands:
            if c.get("verified"):
                continue
            reason = c.get("rejection_reason") or "unknown"
            rejected.append({**c, "layer": layer})
            if reason.startswith("failed_corroboration"):
                rej_corr += 1
            elif reason.startswith("failed_category_fit"):
                rej_fit += 1
            elif reason.startswith("failed_existence"):
                rej_exist += 1

        if not cands:
            status = "no_results"
            warnings.append(
                f"Layer '{layer}': search returned nothing usable, even after a broadened "
                f"query. Kept in the map with an empty company list rather than dropped."
            )
        elif not strong and not weak:
            status = "no_verified_companies"
            warnings.append(
                f"Layer '{layer}': candidates were found but none passed verification "
                f"(see rejected list)."
            )
        elif not strong and weak:
            status = "no_verified_companies"
            warnings.append(
                f"Layer '{layer}': only under-corroborated candidates — see the review "
                f"queue; none placed on the map yet."
            )
        else:
            status = "ok"

        if meta.get("reformulated"):
            n_reformulated += 1
            warnings.append(
                f"Layer '{layer}': the first search came back empty; a broadened query was used."
            )
        if meta.get("over_cap"):
            n_over_cap += 1
            warnings.append(
                f"Layer '{layer}': {meta.get('raw_count')} candidates found, capped at {hard}. "
                f"This layer is probably too broad — consider splitting it."
            )
        elif meta.get("raw_count", 0) > soft:
            warnings.append(
                f"Layer '{layer}': {meta.get('raw_count')} candidates — on the large side; "
                f"a split might read better."
            )

        layers_out.append(
            {
                "name": layer,
                "explanation": llm.layer_explanation(layer, defs.get(layer, ""), adjacent, strong),
                "status": status,
                "companies": strong,
                "under_corroborated_count": len(weak),
                "reformulated": bool(meta.get("reformulated", False)),
                "over_cap": bool(meta.get("over_cap", False)),
            }
        )

    if layers_out and all(l["status"] != "ok" for l in layers_out):
        warnings.append(
            "No layer produced a corroborated company — this usually means the scope is "
            "off. Consider re-running with a rescope."
        )

    final = {
        "topic": state["topic"],
        "zoom_level": scope.get("zoom_level", "company"),
        "layers": layers_out,
        "rejected": rejected,
        "needs_review": needs_review,
        "warnings": warnings,
        "generated_at": now_iso(),
    }

    metrics = {
        "layers": len(layers_out),
        "companies_found": n_found,
        "companies_verified": n_verified,
        "companies_under_corroborated": n_under,
        "rejected_failed_corroboration": rej_corr,
        "rejected_failed_category_fit": rej_fit,
        "rejected_failed_existence": rej_exist,
        "layers_reformulated": n_reformulated,
        "layers_over_cap": n_over_cap,
        "rescope_count": state.get("rescope_count", 0),
        "cap_hit": bool(state.get("cap_hit", False)),
    }

    record = run_log.build_run_record(state, final, metrics)
    run_log.write_run_log(record, get_settings())

    return {"final_output": final, "metrics": metrics}
