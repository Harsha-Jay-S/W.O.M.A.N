"""Persistent query history for the woman CLI."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

HISTORY_FILE = Path.home() / ".cache" / "woman" / "query_history.json"
_MAX_ENTRIES = 500


@dataclass
class HistoryEntry:
    timestamp: float
    query: str
    rendered: str
    action: str  # "execute", "copy", "cancel", "edit"
    os: str


def _load_raw() -> list[dict]:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def append_history(entry: HistoryEntry) -> None:
    entries = _load_raw()
    entries.append(asdict(entry))
    if len(entries) > _MAX_ENTRIES:
        entries = entries[-_MAX_ENTRIES:]
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def load_history(n: int = 50) -> list[HistoryEntry]:
    raw = _load_raw()
    entries = []
    for item in raw[-n:]:
        try:
            entries.append(HistoryEntry(
                timestamp=float(item.get("timestamp", 0)),
                query=str(item.get("query", "")),
                rendered=str(item.get("rendered", "")),
                action=str(item.get("action", "")),
                os=str(item.get("os", "")),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return entries


def last_executed() -> HistoryEntry | None:
    """Return the most recent entry where action == 'execute'."""
    for entry in reversed(load_history(n=_MAX_ENTRIES)):
        if entry.action == "execute":
            return entry
    return None
