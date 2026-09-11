"""Persistent, cross-run company identity. Each layer's search->extract->
corroborate pipeline runs in isolation per run, so without this the same real
company gets re-litigated from scratch by search luck every time it comes up
under a different topic or layer (seen live: Nscale scored 4 independent
sources under one topic, 1 under an adjacent one)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from backend.app import registry
from backend.app.config import Settings

REAL_NO_DB = Settings(use_stubs=False, anthropic_api_key="x", exa_api_key="y", database_url="")
STUB = Settings(use_stubs=True)


@pytest.fixture(autouse=True)
def _isolated_local_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "_LOCAL_REGISTRY", tmp_path / "registry.json")
    yield


def test_stub_mode_is_a_pure_pass_through():
    # Must never touch disk/DB in stub mode -- tests use hand-authored
    # fixtures with exact expected outcomes; registry state leaking across
    # test runs would make them order-dependent.
    name, srcs = registry.merge_and_store(
        name="Acme", url="https://acme.com", new_sources=[{"url": "https://a.com", "title": "t"}],
        topic="T", settings=STUB,
    )
    assert name == "Acme"
    assert srcs == [{"url": "https://a.com", "title": "t"}]
    assert not registry._LOCAL_REGISTRY.exists()


def test_first_encounter_is_stored_as_is():
    name, srcs = registry.merge_and_store(
        name="Nscale", url="https://nscale.com",
        new_sources=[{"url": "https://cnbc.com/a", "title": "t1"}],
        topic="AI infra", settings=REAL_NO_DB,
    )
    assert name == "Nscale"
    assert srcs == [{"url": "https://cnbc.com/a", "title": "t1"}]


def test_second_encounter_under_a_different_topic_accumulates_evidence():
    registry.merge_and_store(
        name="Nscale", url="https://nscale.com",
        new_sources=[{"url": "https://cnbc.com/a", "title": "t1"}],
        topic="AI infra", settings=REAL_NO_DB,
    )
    # Same real company, different topic run, a search that this time only
    # turns up one (different) source -- this is the exact live scenario.
    name, srcs = registry.merge_and_store(
        name="Nscale", url="https://nscale.com",
        new_sources=[{"url": "https://strategy-business.com/b", "title": "t2"}],
        topic="neo-cloud", settings=REAL_NO_DB,
    )
    urls = {s["url"] for s in srcs}
    assert urls == {"https://cnbc.com/a", "https://strategy-business.com/b"}


def test_fuller_name_form_wins_and_is_sticky():
    registry.merge_and_store(name="Together", url="https://together.ai", new_sources=[], topic="T1", settings=REAL_NO_DB)
    name, _ = registry.merge_and_store(name="Together AI", url="https://together.ai", new_sources=[], topic="T2", settings=REAL_NO_DB)
    assert name == "Together AI"
    # and it stays the fuller form even if a later run only extracts the short form
    name, _ = registry.merge_and_store(name="Together", url="https://together.ai", new_sources=[], topic="T3", settings=REAL_NO_DB)
    assert name == "Together AI"


def test_duplicate_sources_do_not_pile_up():
    registry.merge_and_store(
        name="Acme", url="https://acme.com",
        new_sources=[{"url": "https://a.com", "title": "t"}], topic="T1", settings=REAL_NO_DB,
    )
    _, srcs = registry.merge_and_store(
        name="Acme", url="https://acme.com",
        new_sources=[{"url": "https://a.com", "title": "t"}], topic="T2", settings=REAL_NO_DB,
    )
    assert len(srcs) == 1


def test_empty_url_is_a_no_op():
    name, srcs = registry.merge_and_store(name="Acme", url="", new_sources=[{"url": "x"}], topic="T", settings=REAL_NO_DB)
    assert name == "Acme"
    assert srcs == [{"url": "x"}]


def test_a_registry_error_degrades_to_no_memory_not_a_crash(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("disk full")

    monkeypatch.setattr(registry, "_load_local", boom)
    name, srcs = registry.merge_and_store(
        name="Acme", url="https://acme.com", new_sources=[{"url": "https://a.com"}],
        topic="T", settings=REAL_NO_DB,
    )
    assert name == "Acme"
    assert srcs == [{"url": "https://a.com"}]
