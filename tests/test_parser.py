from __future__ import annotations

import shutil
import subprocess

import pytest

from woman_revamp.indexer.parser import _capture, parse_tool


def _man_text(tool: str) -> str:
    if shutil.which("man") is None:
        pytest.skip("man command unavailable")
    completed = subprocess.run(["man", tool], capture_output=True, text=True, check=False)
    text = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if not text.strip():
        pytest.skip(f"no man page available for {tool}")
    return text


def test_capture_limits_real_man_page():
    text = _man_text("find")
    limited = _capture("man", ["find"], limit=300)
    assert limited
    assert limited.count("\n") <= 300
    assert limited == "\n".join(text.splitlines()[:300]) if text.splitlines() else limited


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
