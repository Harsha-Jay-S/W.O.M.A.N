"""Persistent cache for AI provider responses during tool indexing."""

from __future__ import annotations

import json
import time
from pathlib import Path

AI_CACHE_FILE = Path.home() / ".cache" / "woman" / "ai_cache.json"
_CACHE_TTL = 7 * 86400  # 7 days in seconds


def _cache_fresh(path: Path) -> bool:
    """Return True if the cache file exists and is younger than _CACHE_TTL."""
    try:
        return (time.time() - path.stat().st_mtime) < _CACHE_TTL
    except OSError:
        return False


def load_ai_cache() -> dict[str, dict]:
    """Load the AI response cache, returning {} if missing or stale."""
    if not AI_CACHE_FILE.exists() or not _cache_fresh(AI_CACHE_FILE):
        return {}
    try:
        return json.loads(AI_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_ai_cache(cache: dict[str, dict]) -> None:
    """Persist the AI response cache to disk."""
    try:
        AI_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        AI_CACHE_FILE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def ai_cache_key(tool: str, provider: str, model: str, man_hash: str) -> str:
    return f"{tool}:{provider}:{model}:{man_hash[:8]}"
