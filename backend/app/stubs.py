"""Deterministic offline fixtures.

Used when USE_STUBS=true or a live key is missing. The point is a believable
end-to-end run with no network: same shapes the real llm/search functions return.
Three demo topics are hand-written; anything else gets a generic skeleton.
"""
from __future__ import annotations

from typing import Dict, List

_DEMOS: Dict[str, dict] = {
    "ai observability": {
        "proposal": {
            "layers": [
                "Instrumentation & SDKs",
                "Trace & Span Storage",
                "Evaluation & Testing",
                "Monitoring, Alerting & Guardrails",
                "Analytics & Debugging UX",
            ],
            "layer_definitions": {
                "Instrumentation & SDKs": "Libraries and auto-instrumentation that capture prompts, responses, tool calls and latency from an LLM app.",
                "Trace & Span Storage": "Backends that persist LLM traces/spans and make them queryable at scale.",
                "Evaluation & Testing": "Offline and online eval harnesses: datasets, scorers, LLM-as-judge, regression gates in CI.",
                "Monitoring, Alerting & Guardrails": "Live quality/cost/latency monitors plus runtime guardrails on inputs and outputs.",
                "Analytics & Debugging UX": "Dashboards and trace explorers humans use to debug and analyse agent behaviour.",
            },
            "in_scope": [
                "LLM/agent-specific tracing", "prompt & output eval", "token-cost tracking",
                "hallucination / guardrail tooling",
            ],
            "excluded_adjacent": [
                "generic APM (Datadog-style infra metrics)", "model training / MLOps pipelines",
                "vector databases", "data labelling platforms",
            ],
            "zoom_level": "company",
            "open_questions": [
                {
                    "question": "Should 'Guardrails' be its own layer rather than folded into "
                    "Monitoring? It has a distinct vendor set.",
                    "affects": "Monitoring, Alerting & Guardrails",
                    "options": ["Keep as its own layer", "Fold into Monitoring, Alerting & Guardrails"],
                },
                {
                    "question": "Is model-provider-native tooling (e.g. dashboards shipped by an "
                    "LLM API) in scope, or only third-party tools?",
                    "affects": "scope",
                    "options": ["Include model-provider-native tooling", "Only third-party tools"],
                },
            ],
            "notes": "Recon was rich and consistent for this topic; the split below is well-supported.",
        },
        # Source mixes are chosen to exercise the independent-source-count rule
        # (>=2 non-junk domains -> corroborated, regardless of tier -- see
        # sources.assess_sources): most companies clear it with 2-3 well-known
        # outlets; PromptEval sits at exactly 1 (under-corroborated -> review
        # queue); Langfuse deliberately has one tier-3 source (ycombinator.com)
        # PLUS one unclassified-but-real one (heavybit.com) to demonstrate that
        # an uncurated outlet still counts as genuine independent coverage.
        "companies": {
            "Instrumentation & SDKs": [
                {"name": "OpenTelemetry GenAI", "url": "https://opentelemetry.io/docs/specs/semconv/gen-ai/",
                 "sources": ["https://thenewstack.io/opentelemetry-genai", "https://www.infoq.com/news/otel-genai",
                             "https://www.gartner.com/en/documents/observability-standards"]},
                {"name": "Traceloop OpenLLMetry", "url": "https://www.traceloop.com/openllmetry",
                 "sources": ["https://techcrunch.com/2024/traceloop-seed", "https://venturebeat.com/traceloop",
                             "https://www.forrester.com/report/llm-instrumentation"]},
            ],
            "Trace & Span Storage": [
                {"name": "LangSmith", "url": "https://smith.langchain.com",
                 "sources": ["https://techcrunch.com/langchain-series-a", "https://www.theinformation.com/langchain",
                             "https://www.bloomberg.com/news/langchain-valuation"]},
                {"name": "Arize Phoenix", "url": "https://phoenix.arize.com",
                 "sources": ["https://www.gartner.com/ml-observability", "https://techcrunch.com/arize-25m",
                             "https://venturebeat.com/arize-phoenix"]},
                # 2 tier-3 sources (score 2.0) but the URL is fabricated -> rejected at existence
                {"name": "ObscureTrace", "url": "https://obscuretrace.example-fake.io",
                 "sources": ["https://techcrunch.com/obscuretrace", "https://venturebeat.com/obscuretrace"]},
            ],
            "Evaluation & Testing": [
                {"name": "Braintrust", "url": "https://www.braintrust.dev",
                 "sources": ["https://techcrunch.com/braintrust-seed", "https://a16z.com/braintrust-investment",
                             "https://www.wsj.com/tech/braintrust-eval"]},
                # ycombinator.com (tier3) + heavybit.com (unclassified, still counts as a
                # real independent mention) -> 2 independent sources -> corroborated
                {"name": "Langfuse", "url": "https://langfuse.com",
                 "sources": ["https://ycombinator.com/companies/langfuse", "https://langfuse.com/blog",
                             "https://www.heavybit.com/library/langfuse"]},
                # exactly one independent source (a niche forum thread, not on any
                # tier list) -> under-corroborated -> review queue, not the map
                {"name": "PromptEval", "url": "https://prompteval.dev",
                 "sources": ["https://prompteval.dev/changelog",
                             "https://www.reddit.com/r/LocalLLaMA/comments/prompteval_thread"]},
            ],
            "Monitoring, Alerting & Guardrails": [
                {"name": "Guardrails AI", "url": "https://www.guardrailsai.com",
                 "sources": ["https://techcrunch.com/guardrails-ai-seed", "https://thenewstack.io/guardrails-ai",
                             "https://www.forrester.com/report/llm-guardrails"]},
                {"name": "WhyLabs LangKit", "url": "https://whylabs.ai/langkit",
                 "sources": ["https://www.forrester.com/llm-monitoring", "https://venturebeat.com/whylabs-langkit",
                             "https://www.gartner.com/whylabs-langkit"]},
            ],
            "Analytics & Debugging UX": [
                {"name": "Helicone", "url": "https://www.helicone.ai",
                 "sources": ["https://ycombinator.com/companies/helicone", "https://techcrunch.com/helicone-yc",
                             "https://www.bloomberg.com/helicone-open-source"]},
                # well-sourced (score 4.0) but wrong layer -> rejected at category-fit
                {"name": "Pinecone", "url": "https://www.pinecone.io", "_miscategorized": True,
                 "sources": ["https://techcrunch.com/pinecone-100m", "https://www.bloomberg.com/pinecone",
                             "https://www.wsj.com/tech/pinecone"]},
            ],
        },
    },
}

_GENERIC_LAYERS = [
    "Inputs & Enablers", "Core Technology", "Tooling & Integration",
    "Delivery & Channels", "End Applications",
]


def _norm(topic: str) -> str:
    return " ".join(topic.lower().split())


def recon_queries(topic: str) -> List[str]:
    return [
        topic,
        f"{topic} value chain",
        f"{topic} market map",
        f"{topic} leading companies",
        f"{topic} landscape overview",
    ]


_DEMO_OUTLETS = {
    "ai observability": {
        "tier1": ["arxiv.org"],
        "tier2": ["gartner.com", "forrester.com"],
        "tier3": ["latent.space", "swyx.io", "thenewstack.io", "infoq.com"],
    },
}


def credible_outlets(topic: str) -> Dict[str, List[str]]:
    """Recon's job: name the outlets that are tier 1/2/3 *for this topic*."""
    return dict(
        _DEMO_OUTLETS.get(
            _norm(topic),
            {"tier1": [], "tier2": [], "tier3": []},
        )
    )


def web_search(query: str, num_results: int = 8) -> List[dict]:
    return [
        {
            "title": f"[stub] {query} — result {i + 1}",
            "url": f"https://example.com/stub/{abs(hash((query, i))) % 10**8}",
            "text": f"Stubbed snippet about '{query}'. Offline fixture, no network call made.",
            "published_date": None,
        }
        for i in range(min(3, num_results))
    ]


def proposal(topic: str, attempt: int = 1, rescope_notes: str = "") -> dict:
    demo = _DEMOS.get(_norm(topic))
    if demo:
        p = dict(demo["proposal"])
        if rescope_notes:
            p = dict(p)
            p["notes"] = f"{p.get('notes','')} (rescope #{attempt - 1}: '{rescope_notes.strip()}' — adjusted.)"
        return p
    # Generic skeleton for unknown topics.
    return {
        "layers": list(_GENERIC_LAYERS),
        "layer_definitions": {
            l: f"The '{l.lower()}' stage of the {topic} value chain." for l in _GENERIC_LAYERS
        },
        "in_scope": [topic, f"core {topic} providers"],
        "excluded_adjacent": [f"general-purpose infrastructure not specific to {topic}"],
        "zoom_level": "company",
        "open_questions": [
            {
                "question": f"Is '{topic}' meant at the component level or the finished-product level?",
                "affects": "zoom_level",
                "options": ["Component level", "Finished-product / company level"],
            },
            {
                "question": "Which adjacent categories should be treated as out of scope?",
                "affects": "scope",
                "options": [],
            },
        ],
        "notes": (
            "No hand-written fixture for this topic and stub mode is on, so this is a "
            "generic skeleton. Run with real API keys for a substantive proposal."
        ),
    }


# Layers that a hand-written fixture deliberately leaves empty on the first search,
# so query-reformulation (edit d) has something to recover.
_SPARSE_FIRST_PASS = {("ai observability", "Monitoring, Alerting & Guardrails")}


def company_candidates(topic: str, layer: str, definition: str, attempt: int = 1) -> List[dict]:
    if attempt == 1 and (_norm(topic), layer) in _SPARSE_FIRST_PASS:
        return []  # forces Execute to reformulate and try again

    demo = _DEMOS.get(_norm(topic))
    if demo and layer in demo["companies"]:
        out = []
        for c in demo["companies"][layer]:
            out.append({
                "name": c["name"],
                "url": c["url"],
                "sources": [{"url": s, "title": s} for s in c["sources"]],
                "_miscategorized": c.get("_miscategorized", False),
            })
        return out
    # Generic: two plausible-looking placeholders, both corroborated.
    slug = layer.lower().split()[0]
    return [
        {
            "name": f"{topic.title()} {layer.split()[0]} Co",
            "url": f"https://{slug}-{abs(hash((topic, layer))) % 10**6}.example.com",
            "sources": [
                {"url": "https://techcrunch.com/stub-a", "title": f"{topic} {layer} roundup"},
                {"url": "https://www.bloomberg.com/stub-b", "title": f"inside {topic}"},
                {"url": "https://www.reuters.com/stub-c", "title": f"{topic} market note"},
            ],
            "_miscategorized": False,
        },
    ]


def one_liner(name: str, url: str, layer: str = "", definition: str = "") -> str:
    lead = (definition.split(",")[0].split(".")[0].strip().lower() or "operates in this layer")
    return f"{name} {lead}; grounded one-liner is written from retrieved text in real mode (stub)."


def rescope_clarifying_question(notes: str, proposal: dict) -> str:
    return (
        "Which specific layer or boundary is wrong, and what would you expect instead? "
        "For example: 'split X into A and B', or 'Y should be out of scope'."
    )


def normalize_scope(scope: dict) -> dict:
    """Deterministic tidy: trim names, keep order, ensure every layer has a definition.
    Does NOT add/remove layers or touch scope/zoom."""
    layers = [str(l).strip() for l in scope.get("layers", [])]
    defs = dict(scope.get("layer_definitions", {}))
    for l in layers:
        defs.setdefault(l, f"The '{l.lower()}' stage of the value chain.")
    return {
        "layers": layers,
        "layer_definitions": {l: defs[l] for l in layers},
        "in_scope": scope.get("in_scope", []),
        "excluded_adjacent": scope.get("excluded_adjacent", []),
        "zoom_level": scope.get("zoom_level", "company"),
    }


def category_fit(one_liner_text: str, layer: str, definition: str, miscategorized: bool = False) -> tuple:
    if miscategorized:
        return False, f"one-liner describes something outside '{layer}' as defined ({definition[:60]}...)"
    return True, "one-liner is consistent with the layer definition"


def layer_explanation(layer: str, definition: str, adjacent: List[str], companies: List[dict]) -> str:
    n = len(companies)
    return (
        f"{layer}. {definition} It sits between the upstream and downstream layers of the "
        f"chain and currently lists {n} verified {'company' if n == 1 else 'companies'}. "
        f"Adjacent-but-excluded: {', '.join(adjacent) if adjacent else 'none noted'}. "
        f"(Stub explanation — the real Synthesize step writes this with Claude.)"
    )


def resolve_url(url: str) -> dict:
    ok = "example-fake" not in url
    return {"resolves": ok, "final_url": url, "status": 200 if ok else 0}
