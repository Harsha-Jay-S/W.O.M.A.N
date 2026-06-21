"""Heuristic and JIT AI parsing for dynamic registry entries."""

from __future__ import annotations

import re
import subprocess
import json
from dataclasses import dataclass

from .providers import AIProviderSpec, fetch_provider_text


ARG_MAP = {
    "FILE": "file",
    "PATH": "path",
    "DIR": "path",
    "DIRECTORY": "path",
    "FOLDER": "path",
    "TARGET": "target",
    "DEST": "destination",
    "DESTINATION": "destination",
    "OUTPUT": "output",
    "NAME": "name",
    "PATTERN": "pattern",
    "HOST": "host",
    "PORT": "port",
    "PID": "pid",
    "USER": "user",
    "GROUP": "group",
    "SERVICE": "service",
    "MODE": "mode",
    "COUNT": "count",
    "NUM": "count",
    "NUMBER": "count",
    "SIZE": "size",
}

OPTION_RE = re.compile(
    r"(?P<flag>--?[a-zA-Z0-9][\w-]*)(?:[=\s](?P<arg><[^>]+>|\[[^\]]+\]|[A-Z][A-Z0-9_-]*|\{[^}]+\}))?"
)


@dataclass(frozen=True)
class ToolSpec:
    keywords: list[str]
    templates: dict[str, str]
    intent_map: dict[str, str]


@dataclass(frozen=True)
class ParsedManPage:
    tool: str
    synopsis: str
    options: list[dict[str, str]]
    keywords: list[str]


def _placeholder_for(argument: str | None) -> str:
    if not argument:
        return ""
    cleaned = argument.strip("<>{}[]()| ").upper()
    return ARG_MAP.get(cleaned, cleaned.lower())


def _capture(tool: str, args: list[str], limit: int | None = None) -> str:
    try:
        timeout_limit = 30 if tool == "man" else 2
        completed = subprocess.run(
            [tool, *args],
            capture_output=True,
            text=True,
            timeout=timeout_limit,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return ""
    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    text = output.strip()
    if not limit or limit <= 0:
        return text
    lines = text.splitlines()
    if len(lines) <= limit:
        return text
    return "\n".join(lines[:limit])


def _help_text(tool: str, man_page_limit: int = 300) -> str:
    text = _capture(tool, ["--help"], limit=man_page_limit)
    if text:
        return text
    return _capture("man", [tool], limit=man_page_limit)


def _strip_man_markup(text: str) -> str:
    text = re.sub(r"\x08.", "", text)
    text = text.replace("\r", "")
    return text


def extract_sections(text: str) -> dict[str, str]:
    clean = _strip_man_markup(text)
    sections: dict[str, list[str]] = {}
    current = ""
    for line in clean.splitlines():
        header = line.strip().lower()
        if header in {
            "name",
            "synopsis",
            "description",
            "options",
            "commands",
            "examples",
        }:
            current = header
            sections.setdefault(current, [])
            continue
        if current:
            sections.setdefault(current, []).append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def _keywords_from_text(tool: str, text: str) -> list[str]:
    keywords = {tool}
    for line in text.splitlines():
        lower = line.lower()
        if lower.startswith(("name", "usage", "description", "options", "commands")):
            keywords.update(re.findall(r"[a-z][a-z0-9-]{2,}", lower))
        if "--" in line or "-" in line:
            keywords.update(re.findall(r"[a-z][a-z0-9-]{2,}", lower))
    return sorted(keywords)


def _templates_from_text(tool: str, text: str) -> dict[str, str]:
    templates: dict[str, str] = {"default": tool}
    sections = extract_sections(text)
    source = sections.get("options") or text
    for line in source.splitlines():
        if not line.strip():
            continue
        matches = list(OPTION_RE.finditer(line))
        for match in matches:
            flag = match.group("flag")
            argument = _placeholder_for(match.group("arg"))
            if not flag:
                continue
            key = flag.lstrip("-").replace("-", "_")
            if argument:
                templates[key] = f"{tool} {flag} {{{argument}}}"
            else:
                templates[key] = f"{tool} {flag}"
    return templates


def _keywords_from_sections(tool: str, text: str) -> list[str]:
    sections = extract_sections(text)
    keywords = {tool}
    name = sections.get("name", "")
    synopsis = sections.get("synopsis", "")
    description = sections.get("description", "")
    for source in (name, synopsis, description):
        keywords.update(re.findall(r"[a-z][a-z0-9-]{2,}", source.lower()))
    if not keywords:
        return _keywords_from_text(tool, text)
    return sorted(keywords)


def parse_tool_jit(tool: str, man_page_limit: int = 300) -> ParsedManPage:
    text = _help_text(tool, man_page_limit=man_page_limit)
    sections = extract_sections(text)
    synopsis = sections.get("synopsis", "")
    options: list[dict[str, str]] = []
    option_text = sections.get("options", text)
    for line in option_text.splitlines():
        matches = list(OPTION_RE.finditer(line))
        for match in matches:
            flag = match.group("flag")
            argument = _placeholder_for(match.group("arg"))
            if not flag:
                continue
            options.append({"flag": flag, "argument": argument, "line": line.strip()})
    keywords = _keywords_from_sections(tool, text)
    return ParsedManPage(
        tool=tool, synopsis=synopsis, options=options, keywords=keywords
    )


_AI_PROMPT_TEMPLATE = """\
Return ONLY valid JSON matching this schema exactly:
{{
  "tool": "{tool}",
  "keywords": ["search", "locate", "file", "directory"],
  "templates": {{
    "basic":  "{tool} {{path}}",
    "verbose": "{tool} -v {{path}}"
  }},
  "intent_map": {{"search": "basic", "verbose": "verbose"}}
}}

Rules:
- Use {{placeholder}} for user-supplied values
- template keys must be lowercase single words
- keywords: 4-12 terms, lowercase, no punctuation
- No explanation, no markdown, only JSON

Tool to parse: {tool}
Man page (first {limit} lines):
{man_page}
"""


def parse_tool_with_ai(
    tool: str,
    provider: dict[str, str] | AIProviderSpec,
    man_page_limit: int = 300,
    context_hint: dict | None = None,
) -> ParsedManPage:
    import hashlib
    from .ai_cache import ai_cache_key, load_ai_cache, save_ai_cache

    if isinstance(provider, AIProviderSpec):
        spec = provider
    else:
        spec = AIProviderSpec(
            provider=str(provider.get("provider", provider.get("ai_provider", "none"))),
            endpoint=str(provider.get("endpoint", provider.get("ai_endpoint", ""))),
            api_key=str(provider.get("api_key", provider.get("ai_api_key", ""))),
            model=str(provider.get("model", provider.get("ai_backend", ""))),
        )

    # Get man page text first — needed for both the cache key and the prompt
    man_text = _help_text(tool, man_page_limit=man_page_limit)

    # Structured prompt with optional context injection
    context_block = ""
    if context_hint:
        parts = []
        if context_hint.get("os"):
            parts.append(f"OS: {context_hint['os']}")
        if context_hint.get("project_type"):
            parts.append(f"Project type: {context_hint['project_type']}")
        if context_hint.get("recent_files"):
            parts.append(f"Recent files: {', '.join(str(f) for f in context_hint['recent_files'][:5])}")
        if parts:
            context_block = "Context: " + " | ".join(parts) + "\n"

    prompt = context_block + _AI_PROMPT_TEMPLATE.format(
        tool=tool,
        limit=man_page_limit,
        man_page=man_text or "(no man page available)",
    )

    # Check cache before calling the provider
    man_hash = hashlib.md5((man_text or tool).encode()).hexdigest()
    cache_key = ai_cache_key(tool, spec.provider, spec.model, man_hash)
    cache = load_ai_cache()
    if cache_key in cache:
        raw = cache[cache_key].get("raw", "")
    else:
        raw = fetch_provider_text(spec, prompt)
        if raw:
            cache[cache_key] = {"raw": raw}
            save_ai_cache(cache)

    if not raw:
        return parse_tool_jit(tool, man_page_limit=man_page_limit)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return parse_tool_jit(tool, man_page_limit=man_page_limit)

    if not isinstance(parsed, dict):
        return parse_tool_jit(tool, man_page_limit=man_page_limit)

    # Validate required keys
    templates_raw = parsed.get("templates", {})
    keywords_raw = parsed.get("keywords", [])
    if not isinstance(templates_raw, dict) or not isinstance(keywords_raw, list):
        return parse_tool_jit(tool, man_page_limit=man_page_limit)

    keywords = [str(k) for k in keywords_raw if isinstance(k, str)] or [tool]
    templates: dict[str, str] = {k: str(v) for k, v in templates_raw.items() if v}
    if not templates:
        templates = {"default": tool}
    intent_map_raw = parsed.get("intent_map", {})
    intent_map: dict[str, str] = {k: str(v) for k, v in intent_map_raw.items()} if isinstance(intent_map_raw, dict) else {}
    if not intent_map:
        intent_map = {"run": "default", "status": "default", "help": "help"}
    return ToolSpec(keywords=keywords, templates=templates, intent_map=intent_map)


def parse_tool(tool: str, man_page_limit: int = 300) -> ToolSpec:
    text = _help_text(tool, man_page_limit=man_page_limit)
    if not text:
        return ToolSpec(
            keywords=[tool], templates={"default": tool}, intent_map={"run": "default"}
        )
    keywords = _keywords_from_sections(tool, text)
    templates = _templates_from_text(tool, text)
    return ToolSpec(
        keywords=keywords,
        templates=templates,
        intent_map={"run": "default", "status": "default", "help": "help"},
    )
