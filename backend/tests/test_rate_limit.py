"""Public-deploy cost guardrail: a stranger with the link can spend real
Anthropic + Exa credits, so a new run must be capped per-IP and globally
before the graph is ever invoked. Off by default so local dev/tests (every
other test file) are unaffected."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from backend.app import rate_limit
from backend.app.config import Settings

OFF = Settings(use_stubs=True)
PER_IP_2 = Settings(use_stubs=True, daily_run_limit_per_ip=2)
GLOBAL_3 = Settings(use_stubs=True, daily_run_limit_global=3)


def _fake_request(ip: str, forwarded: str | None = None) -> SimpleNamespace:
    headers = {"x-forwarded-for": forwarded} if forwarded else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=ip))


@pytest.fixture(autouse=True)
def _isolated_counts(monkeypatch):
    monkeypatch.setattr(rate_limit, "_counts", {})
    yield


def test_disabled_by_default_never_raises():
    for _ in range(50):
        rate_limit.check_and_record("1.2.3.4", OFF)


def test_per_ip_cap_blocks_the_third_run_from_the_same_ip():
    rate_limit.check_and_record("1.2.3.4", PER_IP_2)
    rate_limit.check_and_record("1.2.3.4", PER_IP_2)
    with pytest.raises(rate_limit.RateLimitExceeded) as exc:
        rate_limit.check_and_record("1.2.3.4", PER_IP_2)
    assert exc.value.scope == "per-IP"


def test_per_ip_cap_is_independent_per_ip():
    rate_limit.check_and_record("1.1.1.1", PER_IP_2)
    rate_limit.check_and_record("1.1.1.1", PER_IP_2)
    # a different IP still has its own budget
    rate_limit.check_and_record("2.2.2.2", PER_IP_2)


def test_global_cap_blocks_even_across_distinct_ips():
    rate_limit.check_and_record("1.1.1.1", GLOBAL_3)
    rate_limit.check_and_record("2.2.2.2", GLOBAL_3)
    rate_limit.check_and_record("3.3.3.3", GLOBAL_3)
    with pytest.raises(rate_limit.RateLimitExceeded) as exc:
        rate_limit.check_and_record("4.4.4.4", GLOBAL_3)
    assert exc.value.scope == "global"


def test_a_blocked_check_does_not_record_a_count():
    with pytest.raises(rate_limit.RateLimitExceeded):
        rate_limit.check_and_record("1.1.1.1", Settings(use_stubs=True, daily_run_limit_per_ip=0))
    # still zero recorded -- raising the *next* call again (not off-by-one)
    with pytest.raises(rate_limit.RateLimitExceeded):
        rate_limit.check_and_record("1.1.1.1", Settings(use_stubs=True, daily_run_limit_per_ip=0))


def test_counts_reset_on_a_new_day(monkeypatch):
    rate_limit.check_and_record("1.1.1.1", PER_IP_2)
    rate_limit.check_and_record("1.1.1.1", PER_IP_2)

    class _Tomorrow:
        @staticmethod
        def today():
            return SimpleNamespace(isoformat=lambda: "2999-01-01")

    monkeypatch.setattr(rate_limit, "date", _Tomorrow)
    # a fresh day means a fresh budget, and yesterday's entries are pruned
    rate_limit.check_and_record("1.1.1.1", PER_IP_2)
    assert all(k[0] == "2999-01-01" for k in rate_limit._counts)


def test_client_ip_prefers_x_forwarded_for_first_hop():
    req = _fake_request("10.0.0.1", forwarded="203.0.113.5, 10.0.0.1")
    assert rate_limit.client_ip(req) == "203.0.113.5"


def test_client_ip_falls_back_to_direct_peer_with_no_proxy():
    req = _fake_request("127.0.0.1")
    assert rate_limit.client_ip(req) == "127.0.0.1"
