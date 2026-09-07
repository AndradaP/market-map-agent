from __future__ import annotations

import os

from .config import Settings


def configure_tracing(settings: Settings) -> bool:
    """Wire LangSmith env vars. Returns True when tracing is active.

    LangGraph and LangChain read these automatically, so every graph node call is
    traced for free. Our own external calls in ``llm.py`` / ``search.py`` are
    decorated with ``@traceable`` so they nest underneath the node spans, giving
    per-run cost, latency and token counts.
    """
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
        os.environ.setdefault("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
        # Legacy aliases some libraries still read.
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
        return True

    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    return False
