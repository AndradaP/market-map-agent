"""Force deterministic stub mode for the whole test suite, regardless of what
`.env` says. Must run before any `get_settings()` call — pytest imports conftest
before collecting tests, so this is early enough.
"""
import os

# Popping a key isn't enough on its own -- pydantic-settings still falls back
# to reading it straight from the .env file when it's merely absent from
# os.environ. Set every secret to an explicit empty string instead, so
# nothing real (a dev's actual keys/DATABASE_URL, left in .env from real-key
# testing) can leak into a test that forgets to pass its own Settings(...)
# override. Found live: this exact gap let a stub-mode test try to open a
# real Postgres connection.
os.environ["USE_STUBS"] = "true"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["EXA_API_KEY"] = ""
os.environ["DATABASE_URL"] = ""
os.environ["LANGSMITH_API_KEY"] = ""

try:
    from backend.app.config import get_settings

    get_settings.cache_clear()
except Exception:  # pragma: no cover
    pass
