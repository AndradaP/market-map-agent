"""One full run, end to end, no network. Confirms the proposal as-is and prints
the final map + the run-log row.

    python -m backend.scripts.run_local "AI observability"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

from backend.app.config import get_settings  # noqa: E402
from backend.app.graph import build_graph  # noqa: E402
from backend.app.tracing import configure_tracing  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "out" / "last_run.json"


def _interrupt_payload(result):
    intr = result.get("__interrupt__")
    if not intr:
        return None
    return getattr(intr[0], "value", intr[0])


def main() -> None:
    topic = sys.argv[1] if len(sys.argv) > 1 else "AI observability"
    settings = get_settings()
    tracing_on = configure_tracing(settings)

    print(f"topic           : {topic}")
    print(f"stub mode       : {settings.stubs_enabled}")
    print(f"langsmith trace : {tracing_on}  (project={settings.langsmith_project})")
    print(f"checkpointer    : {settings.checkpointer_backend}")
    print("-" * 72)

    graph = build_graph(MemorySaver())
    cfg = {"configurable": {"thread_id": "local-demo"}}

    step1 = graph.invoke({"topic": topic, "run_id": "local-demo"}, cfg)
    review = _interrupt_payload(step1)
    assert review, "expected the confirm gate to interrupt"
    p = review["proposal"]
    print("PROPOSAL (attempt {}):".format(review["attempt"]))
    for i, layer in enumerate(p["layers"], 1):
        print(f"  {i}. {layer}")
        print(f"       {p['layer_definitions'].get(layer, '')}")
    print(f"  zoom_level      : {p['zoom_level']}")
    print(f"  in_scope        : {', '.join(p['in_scope'])}")
    print(f"  excluded        : {', '.join(p['excluded_adjacent'])}")
    print(f"  open_questions  : {p.get('open_questions', [])}")
    print(f"  notes           : {p.get('notes', '')}")
    print(
        f"  rescope policy  : {review['rescopes_remaining']} of {review['rescope_cap']} "
        f"rescope requests remaining (stated upfront)"
    )
    print("-" * 72)

    from langgraph.types import Command

    step2 = graph.invoke(
        Command(resume={"type": "none", "notes": "", "different_topic": False, "edited_scope": None}),
        cfg,
    )
    final = step2["final_output"]
    metrics = step2["metrics"]

    print("FINAL MAP:")
    for layer in final["layers"]:
        badges = []
        if layer.get("reformulated"):
            badges.append("broadened-query")
        if layer.get("over_cap"):
            badges.append("too-broad/capped")
        tag = f"   [{layer['status']}]" + (f"  ({', '.join(badges)})" if badges else "")
        print(f"\n## {layer['name']}{tag}")
        print(f"   {layer['explanation']}")
        for c in layer["companies"]:
            corr = c.get("corroboration", {})
            tiers = "/".join(corr.get("tiers", [])) or "?"
            print(f"   - {c['name']}  <{c['url']}>   [{tiers}  score {corr.get('score')}]")
            print(f"       {c['one_liner']}")
            print(f"       sources: {', '.join(c['sources'])}")
        if layer.get("under_corroborated_count"):
            print(f"   ({layer['under_corroborated_count']} under-corroborated -> review queue)")

    if final.get("needs_review"):
        print("\n## Review queue (verified, but under-corroborated — rescue by hand)")
        for c in final["needs_review"]:
            print(f"   - {c['name']} [{c['layer']}] — {c['one_liner']}")
            print(f"       {c.get('corroboration', {}).get('detail')}")

    if final["rejected"]:
        print("\n## Rejected (shown, not silently dropped)")
        for c in final["rejected"]:
            print(f"   - {c['name']} [{c['layer']}]: {c['rejection_reason']}")
    if final["warnings"]:
        print("\n## Warnings")
        for w in final["warnings"]:
            print(f"   - {w}")

    print("\n" + "-" * 72)
    print("RUN-LOG ROW:")
    print(json.dumps(
        {
            "topic": final["topic"],
            "num_layers": metrics["layers"],
            "companies_found": metrics["companies_found"],
            "companies_verified": metrics["companies_verified"],
            "companies_under_corroborated": metrics["companies_under_corroborated"],
            "rejected_failed_corroboration": metrics["rejected_failed_corroboration"],
            "rejected_failed_category_fit": metrics["rejected_failed_category_fit"],
            "rejected_failed_existence": metrics["rejected_failed_existence"],
            "layers_reformulated": metrics["layers_reformulated"],
            "layers_over_cap": metrics["layers_over_cap"],
            "rescope_count": metrics["rescope_count"],
            "cap_hit": metrics["cap_hit"],
        },
        indent=2,
    ))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"final_output": final, "metrics": metrics}, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
