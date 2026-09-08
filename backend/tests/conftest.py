"""Force deterministic stub mode for the whole test suite, regardless of what
`.env` says. Must run before any `get_settings()` call — pytest imports conftest
before collecting tests, so this is early enough.
"""
import os

os.environ["USE_STUBS"] = "true"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("EXA_API_KEY", None)

try:
    from backend.app.config import get_settings

    get_settings.cache_clear()
except Exception:  # pragma: no cover
    pass
