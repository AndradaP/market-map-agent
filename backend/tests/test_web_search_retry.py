"""Exa's real per-second rate limit gets hit routinely once Execute fans out
per-layer AND per-company concurrently (execute.py's layer pool x
find_company_sources' corroboration pool). web_search must absorb a transient
429 instead of crashing the whole run, but must NOT swallow other errors."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from backend.app import search
from backend.app.config import Settings

REAL = Settings(use_stubs=False, anthropic_api_key="x", exa_api_key="y")


class _FakeResult:
    def __init__(self, url):
        self.title, self.url, self.text, self.published_date = "t", url, "txt", None


class _FakeExaResponse:
    def __init__(self, urls):
        self.results = [_FakeResult(u) for u in urls]


def test_rate_limit_error_is_retried_until_it_succeeds(monkeypatch):
    calls = {"n": 0}

    class FakeExa:
        def search_and_contents(self, query, **kw):
            calls["n"] += 1
            if calls["n"] < 2:
                raise ValueError(
                    'Request failed with status code 429: {"error":"...","tag":"RATE_LIMIT_EXCEEDED"}'
                )
            return _FakeExaResponse(["https://example.com/a"])

    monkeypatch.setattr(search, "_exa", lambda settings: FakeExa())

    out = search.web_search("q", settings=REAL)
    assert calls["n"] == 2
    assert out[0]["url"] == "https://example.com/a"


def test_non_rate_limit_error_is_raised_immediately_not_retried(monkeypatch):
    calls = {"n": 0}

    class FakeExa:
        def search_and_contents(self, query, **kw):
            calls["n"] += 1
            raise ValueError("Request failed with status code 401: invalid API key")

    monkeypatch.setattr(search, "_exa", lambda settings: FakeExa())

    with pytest.raises(ValueError, match="401"):
        search.web_search("q", settings=REAL)
    assert calls["n"] == 1
