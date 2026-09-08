"""resolve_url must send a browser-shaped User-Agent: bot-protected real
company sites (Cloudflare and similar WAFs) 403 a bare httpx client outright,
which would wrongly fail the existence check for genuinely real companies
(e.g. openai.com) — see the live-run finding this fixes."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app import search
from backend.app.config import Settings

REAL = Settings(use_stubs=False, anthropic_api_key="x", exa_api_key="y")


class _FakeResponse:
    def __init__(self, status_code, url="https://example.com"):
        self.status_code = status_code
        self.url = url


def test_head_request_carries_a_browser_user_agent(monkeypatch):
    captured = {}

    def fake_head(url, *, headers=None, **kw):
        captured["headers"] = headers
        return _FakeResponse(200)

    monkeypatch.setattr("httpx.head", fake_head)

    search.resolve_url("https://example.com", settings=REAL)
    assert "Mozilla" in captured["headers"]["User-Agent"]


def test_get_fallback_also_carries_the_user_agent(monkeypatch):
    captured = {}

    def fake_head(url, *, headers=None, **kw):
        return _FakeResponse(403)

    def fake_get(url, *, headers=None, **kw):
        captured["headers"] = headers
        return _FakeResponse(200)

    monkeypatch.setattr("httpx.head", fake_head)
    monkeypatch.setattr("httpx.get", fake_get)

    out = search.resolve_url("https://example.com", settings=REAL)
    assert out["resolves"] is True
    assert "Mozilla" in captured["headers"]["User-Agent"]
