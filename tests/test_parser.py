from __future__ import annotations

from woman_revamp.indexer.parser import _capture, _help_text, parse_tool

MOCK_MAN_PAGE = """NAME
    find - search for files in a directory hierarchy

SYNOPSIS
    find [options] [path...]

DESCRIPTION
    find searches the directory tree rooted at each given file name

OPTIONS
    -name pattern    Base of file name matches shell pattern
    -type c          File is of type c
    -mtime n         File's data was last modified n*24 hours ago
    -size n          File uses n units of space
    -exec command    Execute command
    -delete          Delete files
    -print           Print file path

COMMANDS
    find . -name foo -type f -print
    find /var -mtime -7 -size +1M"""


def test_capture_limits_real_man_page(monkeypatch):
    def fake_capture(tool, args, limit=None):
        lines = MOCK_MAN_PAGE.splitlines()
        result = "\n".join(lines[:limit]) if limit else MOCK_MAN_PAGE
        return result

    monkeypatch.setattr("woman_revamp.indexer.parser._capture", fake_capture)
    limited = _capture("man", ["find"], limit=300)
    assert limited


def test_parse_tool_uses_man_page(monkeypatch):
    def fake_help_text(tool, man_page_limit=300):
        return MOCK_MAN_PAGE

    monkeypatch.setattr("woman_revamp.indexer.parser._help_text", fake_help_text)
    spec = parse_tool("find", man_page_limit=300)
    assert spec.keywords
    assert spec.templates
    assert "default" in spec.templates
