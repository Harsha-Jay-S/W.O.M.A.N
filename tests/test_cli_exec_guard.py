"""Guard against non-interactive auto-execution (the --yes / tty footgun)."""

import pytest

import woman_revamp.cli as cli


# ── Unit: the pure decision helper ────────────────────────────────────────────

@pytest.mark.parametrize(
    "interactive,yes,danger,expected",
    [
        (True,  False, 0.0,  "prompt"),   # normal interactive → show menu
        (True,  True,  0.0,  "execute"),  # --yes at a tty → skip menu, run
        (False, False, 0.0,  "print"),    # piped, no --yes → DON'T run (footgun closed)
        (False, True,  0.0,  "execute"),  # piped + --yes → opt-in run
        (False, True,  0.90, "refuse"),   # piped + --yes + dangerous → refuse
        (True,  True,  0.90, "execute"),  # tty + --yes → run (user is watching)
    ],
)
def test_resolve_action_mode(interactive, yes, danger, expected):
    assert cli.resolve_action_mode(interactive, yes, danger) == expected


# ── Integration: the wiring inside main() ─────────────────────────────────────

class _FakeCompleted:
    returncode = 0


def _run(monkeypatch, argv, *, interactive):
    """Run cli.main(argv) with subprocess.run captured and stdin tty faked."""
    calls = []
    monkeypatch.setattr(
        cli.subprocess, "run", lambda *a, **k: calls.append((a, k)) or _FakeCompleted()
    )
    monkeypatch.setattr(
        cli.sys, "stdin",
        type("_S", (), {"isatty": staticmethod(lambda: interactive)})(),
    )
    # Avoid writing to ~/.cache during the execute path.
    import woman_revamp.query_history as qh
    monkeypatch.setattr(qh, "append_history", lambda *a, **k: None)
    rc = cli.main(argv)
    return rc, calls


def test_noninteractive_without_yes_does_not_execute(monkeypatch):
    rc, calls = _run(monkeypatch, ["find", "python", "files"], interactive=False)
    assert calls == [], "command must NOT run non-interactively without --yes"
    assert rc == 0


def test_noninteractive_with_yes_executes(monkeypatch):
    rc, calls = _run(monkeypatch, ["--yes", "find", "python", "files"], interactive=False)
    assert len(calls) == 1, "command should run when --yes is passed"
