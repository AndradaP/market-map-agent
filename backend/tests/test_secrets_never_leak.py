"""A live run found all three real API keys (Anthropic, Exa, LangSmith) sitting
in plaintext inside LangSmith's stored trace data -- every llm.py/search.py
function is @traceable and takes a `settings: Settings` object as an argument,
and LangSmith's tracing serializes full function arguments by default. All
three keys had to be rotated. Settings' secret fields are now SecretStr,
which masks on repr/str/JSON serialization unless code explicitly calls
.get_secret_value() -- this test locks that property in so it can't
regress silently."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.config import Settings

REAL_SECRET = "sk-ant-super-secret-value-do-not-leak"


def _settings():
    return Settings(
        use_stubs=False,
        anthropic_api_key=REAL_SECRET,
        exa_api_key=REAL_SECRET,
        langsmith_api_key=REAL_SECRET,
        database_url=f"postgres://user:{REAL_SECRET}@host/db",
    )


def test_repr_never_shows_the_raw_secret():
    s = _settings()
    assert REAL_SECRET not in repr(s)
    assert REAL_SECRET not in str(s)


def test_model_dump_json_never_shows_the_raw_secret():
    # This is the exact serialization path a tracer (LangSmith or otherwise)
    # takes when it captures a traced function's arguments for upload.
    s = _settings()
    dumped = s.model_dump_json()
    assert REAL_SECRET not in dumped
    parsed = json.loads(dumped)
    assert parsed["anthropic_api_key"] == "**********"
    assert parsed["exa_api_key"] == "**********"
    assert parsed["langsmith_api_key"] == "**********"
    assert REAL_SECRET not in parsed["database_url"]


def test_get_secret_value_still_returns_the_real_key_for_actual_use():
    s = _settings()
    assert s.anthropic_api_key.get_secret_value() == REAL_SECRET
    assert s.exa_api_key.get_secret_value() == REAL_SECRET
    assert s.langsmith_api_key.get_secret_value() == REAL_SECRET
    assert REAL_SECRET in s.database_url.get_secret_value()


def test_falsy_checks_still_work_for_unset_or_empty_secrets():
    # Explicitly override every secret field -- Settings() otherwise falls
    # through to whatever's in the real .env file on disk regardless of which
    # *other* fields this call overrides, which would make this test's result
    # depend on the developer's local secrets rather than what it claims to test.
    empty = Settings(use_stubs=False, anthropic_api_key=None, exa_api_key=None, database_url="")
    assert not empty.anthropic_api_key
    assert not empty.database_url
    assert empty.checkpointer_backend == "memory"
