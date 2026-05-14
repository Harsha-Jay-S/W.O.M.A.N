"""Registry merger for woman_revamp."""

from __future__ import annotations

from functools import lru_cache
from platform import system
from typing import Mapping

from ..config import REGISTRY_CACHE_FILE, read_json
from .linux import COMMANDS as LINUX_COMMANDS
from .macos import COMMANDS as MACOS_COMMANDS
from .shared import COMMANDS as SHARED_COMMANDS
from .windows import COMMANDS as WINDOWS_COMMANDS


def normalize_os_name(name: str | Mapping[str, object] | None) -> str:
    """Normalize common OS labels to linux, macos, or windows."""

    if not name:
        return _normalize_platform(system())
    if isinstance(name, Mapping):
        for key in ("system", "platform", "name", "os", "distro"):
            value = name.get(key)
            if value:
                return _normalize_platform(str(value))
        return _normalize_platform(system())
    return _normalize_platform(name)


def _normalize_platform(name: str) -> str:
    value = name.strip().lower()
    if value in {"darwin", "mac", "macos", "osx", "apple"}:
        return "macos"
    if value in {"windows", "win32", "cygwin", "msys", "mingw"}:
        return "windows"
    return "linux"


def _load_dynamic_registry() -> dict[str, dict]:
    data = read_json(REGISTRY_CACHE_FILE, {})
    if not isinstance(data, dict):
        return {}
    commands = data.get("commands", {})
    if not isinstance(commands, dict):
        return {}
    return {str(name): dict(spec) for name, spec in commands.items() if isinstance(spec, dict)}


@lru_cache(maxsize=8)
def get_registry(os_name: str | None = None) -> dict[str, dict]:
    """Return the merged registry for the requested OS."""

    normalized = normalize_os_name(os_name)
    registry: dict[str, dict] = dict(SHARED_COMMANDS)
    if normalized == "linux":
        registry.update(LINUX_COMMANDS)
    elif normalized == "macos":
        registry.update(MACOS_COMMANDS)
    elif normalized == "windows":
        registry.update(WINDOWS_COMMANDS)
    dynamic = _load_dynamic_registry()
    merged = dict(dynamic)
    merged.update(registry)
    return merged


__all__ = ["get_registry", "normalize_os_name"]
