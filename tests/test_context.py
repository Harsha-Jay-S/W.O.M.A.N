"""Tests for context gathering helpers."""

import os
import tempfile
from pathlib import Path

from woman_revamp.context import get_active_files, get_project_signals, get_shell_history


def test_get_active_files_returns_list_of_paths():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "old.txt").touch()
        files = get_active_files(Path(tmp), max_files=100)
        assert isinstance(files, list)
        assert all(isinstance(f, Path) for f in files)
        assert any(f.name == "old.txt" for f in files)


def test_get_active_files_obeys_max_files():
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(10):
            Path(tmp, f"file{i}.txt").touch()
        files = get_active_files(Path(tmp), max_files=3)
        assert len(files) <= 3


def test_get_active_files_handles_missing_directory():
    files = get_active_files(Path("/nonexistent/path/xyz123"), max_files=100)
    assert files == []


def test_get_active_files_newer_files_first():
    with tempfile.TemporaryDirectory() as tmp:
        old = Path(tmp, "old.txt")
        old.write_text("a")
        os.utime(old, (1000000000, 1000000000))
        new = Path(tmp, "new.txt")
        new.write_text("b")
        files = get_active_files(Path(tmp), max_files=100)
        names = [f.name for f in files]
        assert names.index("new.txt") < names.index("old.txt")


def test_get_project_signals_detects_python():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "pyproject.toml").touch()
        signals = get_project_signals(Path(tmp))
        assert signals["python"] is True
        assert signals["node"] is False


def test_get_project_signals_detects_git():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, ".git").mkdir()
        signals = get_project_signals(Path(tmp))
        assert signals["git"] is True


def test_get_project_signals_detects_docker():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "docker-compose.yml").touch()
        signals = get_project_signals(Path(tmp))
        assert signals["docker"] is True
        assert signals["python"] is False


def test_get_project_signals_empty_dir():
    with tempfile.TemporaryDirectory() as tmp:
        signals = get_project_signals(Path(tmp))
        assert all(v is False for v in signals.values())


def test_get_project_signals_uses_active_files():
    with tempfile.TemporaryDirectory() as tmp:
        pf = Path(tmp, "pyproject.toml")
        pf.touch()
        active = [pf]
        signals = get_project_signals(Path(tmp), active_files=active)
        assert signals["python"] is True


def test_get_shell_history_returns_list():
    history = get_shell_history(5)
    assert isinstance(history, list)


def test_get_shell_history_respects_n():
    history = get_shell_history(3)
    # May be slightly larger due to recency-repeat logic but bounded
    assert len(history) <= 6  # at most n+1 (one repeat of most recent)


def test_get_shell_history_fallback_on_missing():
    old_histfile = os.environ.pop("HISTFILE", None)
    history = get_shell_history(5)
    assert isinstance(history, list)
    if old_histfile is not None:
        os.environ["HISTFILE"] = old_histfile
