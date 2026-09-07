"""Drives the rescope cap end to end: 2 granted rescopes, a 3rd request that is
refused with a stated handoff, then a direct edit that completes the run.

    python -m backend.scripts.demo_rescope_cap
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from backend.app.graph import build_graph  # noqa: E402


def _review(result):
    intr = result.get("__interrupt__")
    return getattr(intr[0], "value", intr[0]) if intr else None


def main() -> None:
    graph = build_graph(MemorySaver())
    cfg = {"configurable": {"thread_id": "rescope-demo"}}

    r = graph.invoke({"topic": "AI observability", "run_id": "rescope-demo"}, cfg)
    review = _review(r)
    print(f"attempt={review['attempt']}  remaining={review['rescopes_remaining']}  "
          f"direct_edit_only={review['direct_edit_only']}")

    for n in (1, 2, 3):
        r = graph.invoke(
            Command(resume={"type": "rescope_request", "notes": f"try #{n}: still too broad",
                            "different_topic": False, "edited_scope": None}),
            cfg,
        )
        review = _review(r)
        assert review is not None, "graph should still be paused at the gate"
        print(f"after rescope #{n}: attempt={review['attempt']}  "
              f"remaining={review['rescopes_remaining']}  "
              f"direct_edit_only={review['direct_edit_only']}  "
              f"handoff={review['handoff_message']!r}")

    # Cap hit -> only a direct edit (or plain confirm) gets us out.
    edited = {
        "layers": ["Instrumentation & SDKs", "Storage", "Evaluation"],
        "layer_definitions": {
            "Instrumentation & SDKs": "capture layer",
            "Storage": "trace storage layer",
            "Evaluation": "eval harness layer",
        },
        "in_scope": ["llm tracing"],
        "excluded_adjacent": ["generic APM"],
        "zoom_level": "company",
    }
    r = graph.invoke(
        Command(resume={"type": "direct_edit", "notes": "", "different_topic": False,
                        "edited_scope": edited}),
        cfg,
    )
    final = r["final_output"]
    m = r["metrics"]
    print("\ncompleted after direct-edit takeover")
    print(f"  layers          : {[l['name'] for l in final['layers']]}")
    print(f"  rescope_count    : {m['rescope_count']}   (cap was 2)")
    print(f"  cap_hit          : {m['cap_hit']}")
    assert m["rescope_count"] == 2, m
    assert m["cap_hit"] is True, m
    print("\nOK — cap enforced: 3 propose attempts total, no 4th, handoff was stated.")


if __name__ == "__main__":
    main()
