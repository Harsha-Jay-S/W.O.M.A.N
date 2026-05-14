"""Lightweight AI provider HTTP helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request


@dataclass(frozen=True)
class AIProviderSpec:
    provider: str
    endpoint: str
    api_key: str = ""
    model: str = ""


def _json_request(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any] | None:
    req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers or {"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (error.URLError, TimeoutError, OSError, ValueError):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def provider_spec_from_config(config: object) -> AIProviderSpec:
    provider = str(getattr(config, "ai_provider", "none") or "none")
    endpoint = str(getattr(config, "ai_endpoint", "") or "")
    api_key = str(getattr(config, "ai_api_key", "") or "")
    model = str(getattr(config, "ai_backend", "") or "")
    return AIProviderSpec(provider=provider, endpoint=endpoint, api_key=api_key, model=model)


def build_provider_payload(spec: AIProviderSpec, prompt: str) -> tuple[str, dict[str, Any], dict[str, str]] | None:
    provider = spec.provider.lower()
    if provider == "ollama":
        endpoint = spec.endpoint.rstrip("/") or "http://localhost:11434"
        return (
            f"{endpoint}/api/generate",
            {"model": spec.model or "llama3", "prompt": prompt, "stream": False},
            {"Content-Type": "application/json"},
        )
    if provider == "openai":
        return (
            spec.endpoint.rstrip("/") or "https://api.openai.com/v1/chat/completions",
            {"model": spec.model or "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0},
            {"Content-Type": "application/json", "Authorization": f"Bearer {spec.api_key}"},
        )
    if provider == "anthropic":
        return (
            spec.endpoint.rstrip("/") or "https://api.anthropic.com/v1/messages",
            {"model": spec.model or "claude-3-5-haiku-latest", "max_tokens": 1500, "messages": [{"role": "user", "content": prompt}]},
            {"Content-Type": "application/json", "x-api-key": spec.api_key, "anthropic-version": "2023-06-01"},
        )
    if provider == "gemini":
        endpoint = spec.endpoint.rstrip("/")
        if not endpoint:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{spec.model or 'gemini-1.5-flash'}:generateContent?key={spec.api_key}"
        elif "key=" not in endpoint and spec.api_key:
            endpoint = f"{endpoint}?key={spec.api_key}"
        return (
            endpoint,
            {"contents": [{"parts": [{"text": prompt}]}]},
            {"Content-Type": "application/json"},
        )
    return None


def fetch_provider_text(spec: AIProviderSpec, prompt: str) -> str:
    payload = build_provider_payload(spec, prompt)
    if not payload:
        return ""
    url, body, headers = payload
    parsed = _json_request(url, body, headers)
    if not parsed:
        return ""
    provider = spec.provider.lower()
    if provider == "ollama":
        return str(parsed.get("response", ""))
    if provider == "openai":
        choices = parsed.get("choices", [])
        if choices and isinstance(choices, list):
            message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
            return str(message.get("content", ""))
        return ""
    if provider == "anthropic":
        content = parsed.get("content", [])
        if content and isinstance(content, list):
            first = content[0]
            if isinstance(first, dict):
                return str(first.get("text", ""))
        return ""
    if provider == "gemini":
        candidates = parsed.get("candidates", [])
        if candidates and isinstance(candidates, list):
            content = candidates[0].get("content", {}) if isinstance(candidates[0], dict) else {}
            parts = content.get("parts", []) if isinstance(content, dict) else []
            if parts and isinstance(parts, list):
                first = parts[0]
                if isinstance(first, dict):
                    return str(first.get("text", ""))
        return ""
    return ""
