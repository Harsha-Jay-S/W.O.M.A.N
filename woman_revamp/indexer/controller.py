"""User-facing indexing commands."""

from __future__ import annotations

from ..registry import get_registry, normalize_os_name
from .cache import load_cached_registry, refresh_registry_cache
from .parser import parse_tool, parse_tool_with_ai
from .providers import AIProviderSpec
from ..config import REGISTRY_CACHE_FILE, write_json


def index_one(tool: str, provider: AIProviderSpec | None = None, ai_mode: bool = False, man_page_limit: int = 300) -> dict[str, dict]:
    if ai_mode and provider and provider.provider != "none":
        spec = parse_tool_with_ai(tool, provider, man_page_limit=man_page_limit)
    else:
        spec = parse_tool(tool, man_page_limit=man_page_limit)
    cached = load_cached_registry()
    cached[tool] = {
        "keywords": spec.keywords,
        "templates": spec.templates,
        "intent_map": spec.intent_map,
    }
    write_json(REGISTRY_CACHE_FILE, {"commands": cached})
    get_registry.cache_clear()
    return cached


def refresh_all(provider: AIProviderSpec | None = None, ai_mode: bool = False, man_page_limit: int = 300) -> dict[str, dict]:
    return refresh_registry_cache(provider=provider, ai_mode=ai_mode, man_page_limit=man_page_limit)
