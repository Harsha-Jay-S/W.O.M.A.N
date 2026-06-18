from __future__ import annotations

import shutil
import subprocess

import pytest

from woman_revamp.indexer.parser import _capture, parse_tool


def _man_text(tool: str) -> str:
    if shutil.which("man") is None:
        pytest.skip("man command unavailable")
    completed = subprocess.run(
        ["man", tool], capture_output=True, text=True, check=False
    )
    text = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if not text.strip():
        pytest.skip(f"no man page available for {tool}")
    return text


def test_capture_limits_real_man_page():
    text = _man_text("find")
    limited = _capture("man", ["find"], limit=300)
    assert limited
    assert limited.count("\n") <= 300
    assert (
        limited == "\n".join(text.splitlines()[:300]) if text.splitlines() else limited
    )


def test_parse_tool_uses_real_man_page(monkeypatch):
    text = _man_text("find")

    def fake_run(cmd, capture_output=True, timeout=2, check=False, **kwargs):
        if cmd[:2] == ["find", "--help"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["man", "find"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=text, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("woman_revamp.indexer.parser.subprocess.run", fake_run)
    spec = parse_tool("find", man_page_limit=300)
    assert spec.keywords
    assert spec.templates
    assert "default" in spec.templates


class TestAICache:

    def test_load_empty_cache(self, tmp_path, monkeypatch):
        from woman_revamp.indexer import ai_cache as _ac
        monkeypatch.setattr(_ac, "AI_CACHE_FILE", tmp_path / "ai_cache.json")
        assert _ac.load_ai_cache() == {}

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        from woman_revamp.indexer import ai_cache as _ac
        monkeypatch.setattr(_ac, "AI_CACHE_FILE", tmp_path / "ai_cache.json")
        data = {"find:ollama:llama3:abc12345": {"raw": '{"tool": "find"}'}}
        _ac.save_ai_cache(data)
        loaded = _ac.load_ai_cache()
        assert loaded == data

    def test_cache_key_format(self):
        from woman_revamp.indexer.ai_cache import ai_cache_key
        key = ai_cache_key("find", "ollama", "llama3", "abc12345678")
        assert key == "find:ollama:llama3:abc12345"

    def test_parse_tool_with_ai_uses_cache(self, tmp_path, monkeypatch):
        from woman_revamp.indexer import ai_cache as _ac
        from woman_revamp.indexer.parser import parse_tool_with_ai
        from woman_revamp.indexer.providers import AIProviderSpec

        monkeypatch.setattr(_ac, "AI_CACHE_FILE", tmp_path / "ai_cache.json")

        call_count = {"n": 0}

        def fake_fetch(spec, prompt):
            call_count["n"] += 1
            return '{"tool":"find","keywords":["search","file"],"templates":{"basic":"find {path}"},"intent_map":{}}'

        monkeypatch.setattr("woman_revamp.indexer.parser.fetch_provider_text", fake_fetch)
        monkeypatch.setattr("woman_revamp.indexer.parser._help_text", lambda *a, **kw: "find(1)\n--name FILE")

        spec = AIProviderSpec(provider="ollama", endpoint="", api_key="", model="llama3")
        result1 = parse_tool_with_ai("find", spec)
        result2 = parse_tool_with_ai("find", spec)

        # Provider should only be called once; second call is cache hit
        assert call_count["n"] == 1
        assert "search" in result1.keywords
