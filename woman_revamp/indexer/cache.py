"""Registry cache management."""

from __future__ import annotations

from dataclasses import dataclass
import json
import shutil
from pathlib import Path
from typing import Any

from ..config import REGISTRY_CACHE_FILE, STATE_FILE, ensure_directories, read_json, write_json
from .parser import parse_tool, parse_tool_with_ai
from .providers import AIProviderSpec
from .scanner import discover_path_tools, snapshot_path_state


@dataclass(frozen=True)
class RegistryState:
    path_snapshot: dict[str, float]
    tools: list[str]


def load_cached_registry() -> dict[str, dict]:
    data = read_json(REGISTRY_CACHE_FILE, {})
    if isinstance(data, dict):
        commands = data.get("commands", {})
        if isinstance(commands, dict):
            return {str(name): dict(spec) for name, spec in commands.items() if isinstance(spec, dict)}
    return {}


def _load_state() -> RegistryState:
    data = read_json(STATE_FILE, {})
    if not isinstance(data, dict):
        data = {}
    snapshot = data.get("path_snapshot", {})
    tools = data.get("tools", [])
    if not isinstance(snapshot, dict):
        snapshot = {}
    if not isinstance(tools, list):
        tools = []
    return RegistryState(path_snapshot={str(k): float(v) for k, v in snapshot.items()}, tools=[str(item) for item in tools])


def registry_needs_refresh() -> bool:
    state = _load_state()
    current = snapshot_path_state()
    if current != state.path_snapshot:
        return True
    current_tools = discover_path_tools()
    return current_tools != state.tools


def _build_dynamic_registry(tools: list[str], provider: AIProviderSpec | None = None, ai_mode: bool = False, man_page_limit: int = 300) -> dict[str, dict]:
    commands: dict[str, dict] = {}
    for name in tools:
        if not shutil.which(name):
            continue
        if ai_mode and provider and provider.provider != "none":
            spec = parse_tool_with_ai(name, provider, man_page_limit=man_page_limit)
        else:
            spec = parse_tool(name, man_page_limit=man_page_limit)
        commands[name] = {
            "keywords": spec.keywords,
            "templates": spec.templates,
            "intent_map": spec.intent_map,
        }
    return commands


def refresh_registry_cache(provider: AIProviderSpec | None = None, ai_mode: bool = False, man_page_limit: int = 300) -> dict[str, dict]:
    ensure_directories()
    tools = discover_path_tools()
    current_state = snapshot_path_state()
    commands = _build_dynamic_registry(tools, provider=provider, ai_mode=ai_mode, man_page_limit=man_page_limit)
    write_json(REGISTRY_CACHE_FILE, {"commands": commands})
    write_json(STATE_FILE, {"path_snapshot": current_state, "tools": tools})
    from ..registry import get_registry

    get_registry.cache_clear()
    return commands
