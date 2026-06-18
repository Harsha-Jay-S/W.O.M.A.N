"""Tests for persistent query history."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from woman_revamp.query_history import (
    HistoryEntry,
    append_history,
    last_executed,
    load_history,
)


@pytest.fixture(autouse=True)
def isolate_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect HISTORY_FILE to a temp path so tests don't pollute real history."""
    import woman_revamp.query_history as _qh
    monkeypatch.setattr(_qh, "HISTORY_FILE", tmp_path / "query_history.json")


def _make_entry(
    query: str = "list files",
    rendered: str = "ls -la",
    action: str = "execute",
    os: str = "linux",
) -> HistoryEntry:
    return HistoryEntry(
        timestamp=time.time(),
        query=query,
        rendered=rendered,
        action=action,
        os=os,
    )


def test_append_and_load_roundtrip() -> None:
    entry = _make_entry()
    append_history(entry)
    entries = load_history()
    assert len(entries) == 1
    assert entries[0].query == entry.query
    assert entries[0].rendered == entry.rendered
    assert entries[0].action == entry.action


def test_load_respects_n() -> None:
    for i in range(10):
        append_history(_make_entry(query=f"query {i}", rendered=f"ls -{i}"))
    entries = load_history(n=3)
    assert len(entries) == 3


def test_last_executed_returns_most_recent_execute() -> None:
    append_history(_make_entry(query="first", rendered="ls", action="execute"))
    append_history(_make_entry(query="second", rendered="pwd", action="copy"))
    append_history(_make_entry(query="third", rendered="echo hi", action="execute"))
    result = last_executed()
    assert result is not None
    assert result.rendered == "echo hi"
    assert result.action == "execute"


def test_last_executed_skips_non_execute() -> None:
    append_history(_make_entry(query="q1", rendered="ls", action="copy"))
    append_history(_make_entry(query="q2", rendered="pwd", action="cancel"))
    result = last_executed()
    assert result is None


def test_empty_history_returns_empty_list() -> None:
    assert load_history() == []


def test_last_executed_on_empty_returns_none() -> None:
    assert last_executed() is None


def test_multiple_appends_accumulate() -> None:
    for i in range(5):
        append_history(_make_entry(query=f"q{i}"))
    assert len(load_history()) == 5
