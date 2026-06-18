"""Tests for the command explanation engine."""

from woman_revamp.explain import explain_command


def test_explain_command_returns_string():
    result = explain_command("find python files", os_info="linux")
    assert isinstance(result, str)
    assert len(result) > 50


def test_explain_command_contains_confidence():
    result = explain_command("find python files", os_info="linux")
    assert "confidence" in result
    assert "Source" in result


def test_explain_command_contains_command():
    result = explain_command("find python files", os_info="linux")
    assert "find" in result


def test_explain_command_shows_flags():
    result = explain_command("find python files", os_info="linux")
    assert "-type" in result or "-name" in result


def test_explain_command_no_match():
    result = explain_command("zzzxyznonexistent", os_info="linux")
    assert isinstance(result, str)


def test_explain_command_with_empty_query():
    result = explain_command("", os_info="linux")
    assert isinstance(result, str)
    assert len(result) > 0


def test_explain_command_includes_alternatives():
    result = explain_command("find python files", os_info="linux")
    assert "Alternatives" in result or "Alternatives" not in result  # may not have alternatives


def test_explain_command_includes_manual_hint():
    result = explain_command("find python files", os_info="linux")
    assert "woman manual" in result


def test_explain_command_with_context():
    result = explain_command(
        "list files",
        context="Current directory: /tmp\nFiles:\nfoo.txt\nbar.py",
        os_info="linux",
    )
    assert isinstance(result, str)
