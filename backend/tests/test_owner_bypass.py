"""Every rate-limited request -- even one that crashes mid-run, as the real
truncation bug did live -- still burns one of the daily slots, since the cap
has to fire before money is spent on the API call, not after seeing whether
it succeeded. That's correct for a cost gate, but the owner still needs a
way around their own cap: a header-carried token, set once via the browser's
own localStorage (see frontend/src/api.js), never checked into git or built
into the public JS bundle."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app import main
from backend.app.config import Settings

WITH_TOKEN = Settings(use_stubs=True, rate_limit_bypass_token="secret123")
NO_TOKEN = Settings(use_stubs=True)


def _fake_request(header_value: str | None = None) -> SimpleNamespace:
    headers = {"x-owner-token": header_value} if header_value is not None else {}
    return SimpleNamespace(headers=headers)


def test_matching_header_is_the_owner():
    assert main._is_owner(_fake_request("secret123"), WITH_TOKEN) is True


def test_wrong_or_missing_header_is_not_the_owner():
    assert main._is_owner(_fake_request("wrong"), WITH_TOKEN) is False
    assert main._is_owner(_fake_request(None), WITH_TOKEN) is False


def test_no_configured_token_means_no_bypass_ever():
    # Even a header that happens to match nothing (token unset) never bypasses.
    assert main._is_owner(_fake_request("secret123"), NO_TOKEN) is False
    assert main._is_owner(_fake_request(None), NO_TOKEN) is False
