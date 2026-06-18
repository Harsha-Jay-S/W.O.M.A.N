"""Shell history and runtime context helpers."""

from __future__ import annotations

import os
import time
from pathlib import Path

PROJECT_SENTINELS: dict[str, frozenset[str]] = {
    "git":    frozenset({".git"}),
    "docker": frozenset({"docker-compose.yml", "docker-compose.yaml", "Dockerfile"}),
    "python": frozenset({"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"}),
    "node":   frozenset({"package.json"}),
    "rust":   frozenset({"Cargo.toml"}),
    "go":     frozenset({"go.mod"}),
    "make":   frozenset({"Makefile", "GNUmakefile"}),
    "venv":   frozenset({".venv", "venv", ".env"}),
}


def get_shell_history(n: int = 5) -> list[str]:
    candidates = []
    histfile = os.environ.get("HISTFILE")
    if histfile:
        candidates.append(Path(histfile).expanduser())
    candidates += [
        Path.home() / ".bash_history",
        Path.home() / ".zsh_history",
        Path.home() / ".history",
        Path.home() / ".local" / "share" / "fish" / "fish_history",
        Path.home()
        / "AppData"
        / "Roaming"
        / "Microsoft"
        / "Windows"
        / "PowerShell"
        / "PSReadLine"
        / "ConsoleHost_history.txt",
        Path.home()
        / ".local"
        / "share"
        / "powershell"
        / "PSReadLine"
        / "ConsoleHost_history.txt",
        Path.home()
        / ".config"
        / "powershell"
        / "PSReadLine"
        / "ConsoleHost_history.txt",
    ]

    for path in candidates:
        if not path.exists():
            continue
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8", errors="replace")
        except OSError:
            continue

        commands: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith(": ") and ";" in line:
                line = line.split(";", 1)[1]
            if line.startswith("- cmd:"):
                line = line[len("- cmd:") :].strip()
            elif line.startswith("  when:"):
                continue
            commands.append(line)
        raw_commands = commands[-n:] if len(commands) >= n else commands
        # Repeat the most recent command to double its TF-IDF weight
        if raw_commands:
            return [raw_commands[-1]] + raw_commands
        return raw_commands
    return []


NOW = time.time()
DAY = 86400


def get_active_files(cwd: Path, max_files: int = 200) -> list[Path]:
    """Return directory entries as Path objects sorted by recency, then by extension presence."""
    all_entries: list[Path] = []
    try:
        all_entries = list(cwd.iterdir())
    except OSError:
        return []

    def sort_key(p: Path) -> tuple:
        try:
            stat = p.stat()
            age = NOW - stat.st_mtime
        except OSError:
            age = float("inf")
        is_recent = age < 7 * DAY
        has_ext = bool(p.suffix)
        return (0 if is_recent else 1, 0 if has_ext else 1, age)

    return sorted(all_entries, key=sort_key)[:max_files]


def get_project_signals(cwd: Path, active_files: list[Path] | None = None) -> dict[str, bool]:
    """Detect project type by scanning cwd for sentinel files."""
    if active_files is None:
        try:
            names = {p.name for p in cwd.iterdir()}
        except OSError:
            names = set()
    else:
        names = {p.name for p in active_files}

    return {
        project: bool(names & sentinels)
        for project, sentinels in PROJECT_SENTINELS.items()
    }
