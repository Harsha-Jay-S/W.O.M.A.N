"""Configuration and cache helpers for woman_revamp."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


APP_NAME = "woman"
CONFIG_DIR = Path.home() / ".config" / APP_NAME
CACHE_DIR = Path.home() / ".cache" / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"
REGISTRY_CACHE_FILE = CACHE_DIR / "registry.json"
STATE_FILE = CACHE_DIR / "state.json"


def ensure_directories() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data: Any) -> None:
    ensure_directories()
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass
class WomanConfig:
    ui_mode: str = "rich"
    ai_provider: str = "none"
    ai_backend: str = ""
    ai_endpoint: str = ""
    ai_api_key: str = ""
    auto_update_registry: bool = True
    auto_refresh_prompt: bool = True
    index_mode: str = "jit"
    man_page_limit: int = 300

    @classmethod
    def load(cls) -> "WomanConfig":
        data = read_json(CONFIG_FILE, {})
        if not isinstance(data, dict):
            data = {}
        kwargs: dict[str, object] = {}
        hints = cls.__annotations__
        for key in hints:
            default = getattr(cls, key)
            value = data.get(key, default)
            try:
                expected = type(default)
                if not isinstance(value, expected):
                    value = expected(value)
            except (TypeError, ValueError):
                value = default
            kwargs[key] = value
        return cls(**kwargs)

    def save(self) -> None:
        write_json(CONFIG_FILE, asdict(self))

    @classmethod
    def defaults(cls) -> "WomanConfig":
        """Return a usable config with sensible defaults, no file required."""
        return cls(
            ui_mode="basic",
            ai_provider="none",
            ai_backend="",
            ai_endpoint="",
            ai_api_key="",
            auto_update_registry=True,
            auto_refresh_prompt=False,
            index_mode="jit",
            man_page_limit=300,
        )


def load_config() -> WomanConfig:
    return WomanConfig.load()
