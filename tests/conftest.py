"""Shared pytest fixtures for woman_revamp tests."""

from __future__ import annotations

import pytest
import woman_revamp.registry as _reg
import woman_revamp.engine as _eng


@pytest.fixture(autouse=True)
def isolate_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent the dynamic registry cache (~/.cache/woman/registry.json) from
    polluting test results.  Auto-indexed PATH tools (e.g. brltty, alsactl)
    accumulate spurious scoring from single-character template keys that match
    as substrings in any query word, outranking curated registry entries."""
    monkeypatch.setattr(_reg, "_load_dynamic_registry", lambda: {})
    _reg.get_registry.cache_clear()
    _eng._scorer_cache.clear()
    _eng._vocab_cache.clear()
    yield
    _reg.get_registry.cache_clear()
    _eng._scorer_cache.clear()
    _eng._vocab_cache.clear()
