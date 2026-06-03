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
        completed = subprocess.run([tool, *args], capture_output=True, text=True, timeout=timeout_limit, check=False)
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
        if header in {"name", "synopsis", "description", "options", "commands", "examples"}:
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
    return ParsedManPage(tool=tool, synopsis=synopsis, options=options, keywords=keywords)


def parse_tool_with_ai(tool: str, provider: dict[str, str] | AIProviderSpec, man_page_limit: int = 300) -> ParsedManPage:
    if isinstance(provider, AIProviderSpec):
        spec = provider
    else:
        spec = AIProviderSpec(
            provider=str(provider.get("provider", provider.get("ai_provider", "none"))),
            endpoint=str(provider.get("endpoint", provider.get("ai_endpoint", ""))),
            api_key=str(provider.get("api_key", provider.get("ai_api_key", ""))),
            model=str(provider.get("model", provider.get("ai_backend", ""))),
        )
    prompt = (
        f"Return strict JSON for the command '{tool}' with keys tool, synopsis, keywords, options. "
        "options must be a list of objects containing flag, argument, and template."
    )
    raw = fetch_provider_text(spec, prompt)
    if not raw:
        return parse_tool_jit(tool, man_page_limit=man_page_limit)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return parse_tool_jit(tool, man_page_limit=man_page_limit)
    options = parsed.get("options", []) if isinstance(parsed, dict) else []
    normalized: list[dict[str, str]] = []
    for item in options if isinstance(options, list) else []:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "flag": str(item.get("flag", "")),
                "argument": str(item.get("argument", "")),
                "line": str(item.get("template", "")),
            }
        )
    synopsis = str(parsed.get("synopsis", "")) if isinstance(parsed, dict) else ""
    keywords = [str(item) for item in parsed.get("keywords", [])] if isinstance(parsed, dict) else [tool]
    return ParsedManPage(tool=tool, synopsis=synopsis, options=normalized, keywords=keywords or [tool])


def parse_tool(tool: str, man_page_limit: int = 300) -> ToolSpec:
    text = _help_text(tool, man_page_limit=man_page_limit)
    if not text:
        return ToolSpec(keywords=[tool], templates={"default": tool}, intent_map={"run": "default"})
    keywords = _keywords_from_sections(tool, text)
    templates = _templates_from_text(tool, text)
    return ToolSpec(keywords=keywords, templates=templates, intent_map={"run": "default", "status": "default", "help": "help"})
