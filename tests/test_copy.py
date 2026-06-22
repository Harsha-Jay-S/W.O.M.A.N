"""Tests for clipboard copy, including the helper-free OSC 52 fallback."""

from __future__ import annotations

import base64

import woman_revamp.cli as cli


def _record_runs(monkeypatch, present="wl-copy"):
    calls = []
    monkeypatch.setattr(cli.sys, "platform", "linux")
    monkeypatch.setattr(
        cli.shutil, "which",
        lambda name: f"/usr/bin/{name}" if name == present else None,
    )

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs.get("input")))
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    return calls


def test_copy_uses_helper_when_present(monkeypatch):
    """A present clipboard helper is invoked and reported as success."""
    calls = _record_runs(monkeypatch, present="wl-copy")
    assert cli._copy_to_clipboard("echo hi") is True
    assert calls[0][0][0] == "wl-copy"
    assert calls[0][1] == b"echo hi"


def test_copy_sets_both_clipboard_and_primary_on_wayland(monkeypatch):
    """Middle-click paste reads the *primary* selection, so set both buffers."""
    calls = _record_runs(monkeypatch, present="wl-copy")
    assert cli._copy_to_clipboard("echo hi") is True
    argvs = [argv for argv, _ in calls]
    assert ["wl-copy"] in argvs
    assert ["wl-copy", "--primary"] in argvs


def test_copy_sets_both_selections_with_xclip(monkeypatch):
    calls = _record_runs(monkeypatch, present="xclip")
    assert cli._copy_to_clipboard("echo hi") is True
    argvs = [argv for argv, _ in calls]
    assert ["xclip", "-selection", "clipboard"] in argvs
    assert ["xclip", "-selection", "primary"] in argvs


def test_copy_succeeds_even_if_primary_selection_fails(monkeypatch):
    """A failure setting the secondary (primary) buffer must not fail the copy."""
    monkeypatch.setattr(cli.sys, "platform", "linux")
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/wl-copy" if name == "wl-copy" else None)

    def fake_run(argv, **kwargs):
        if "--primary" in argv:
            raise cli.subprocess.CalledProcessError(1, argv)
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli._copy_to_clipboard("echo hi") is True


def test_osc52_emits_correct_escape_sequence(capsys):
    """OSC 52 fallback base64-encodes the command into an OSC 52 sequence."""
    cmd = "zip -r archive.zip */"
    ok = cli._osc52_copy(cmd, is_tty=True, tmux=False)
    assert ok is True
    out = capsys.readouterr().out
    b64 = base64.b64encode(cmd.encode()).decode()
    assert "\x1b]52;c;" in out
    assert b64 in out
    assert out.rstrip().endswith("\x07")


def test_osc52_wraps_for_tmux(capsys):
    cli._osc52_copy("ls", is_tty=True, tmux=True)
    out = capsys.readouterr().out
    assert out.startswith("\x1bPtmux;")
    assert out.rstrip().endswith("\x1b\\")


def test_osc52_noop_when_not_a_tty(capsys):
    assert cli._osc52_copy("ls", is_tty=False, tmux=False) is False
    assert capsys.readouterr().out == ""


def test_copy_falls_back_to_osc52_when_no_helper(monkeypatch, capsys):
    """No helper binary but a TTY → command still reaches the terminal clipboard."""
    monkeypatch.setattr(cli.sys, "platform", "linux")
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    assert cli._copy_to_clipboard("echo hi") is True
    assert "\x1b]52;c;" in capsys.readouterr().out


def test_copy_returns_false_when_no_helper_and_no_tty(monkeypatch):
    monkeypatch.setattr(cli.sys, "platform", "linux")
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: False)
    assert cli._copy_to_clipboard("echo hi") is False
