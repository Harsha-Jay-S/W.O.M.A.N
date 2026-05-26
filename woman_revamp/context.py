"""Shell history and runtime context helpers."""

from __future__ import annotations

import os
from pathlib import Path


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
        Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt",
        Path.home() / ".local" / "share" / "powershell" / "PSReadLine" / "ConsoleHost_history.txt",
        Path.home() / ".config" / "powershell" / "PSReadLine" / "ConsoleHost_history.txt",
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
                line = line[len("- cmd:"):].strip()
            elif line.startswith("  when:"):
                continue
            commands.append(line)
        return commands[-n:] if len(commands) >= n else commands
    return []
