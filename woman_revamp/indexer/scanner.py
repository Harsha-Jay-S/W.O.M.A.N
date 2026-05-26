"""PATH scanning helpers."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def _iter_path_dirs() -> list[Path]:
    dirs: list[Path] = []
    for raw in os.environ.get("PATH", "").split(os.pathsep):
        if raw:
            path = Path(raw).expanduser()
            if path.is_dir():
                dirs.append(path)
    return dirs


def discover_path_tools() -> list[str]:
    tools: list[str] = []
    seen: set[str] = set()
    pathext = {
        ext.lower()
        for ext in os.environ.get("PATHEXT", ".EXE;.BAT;.CMD;.COM").split(os.pathsep)
        if ext
    }
    for directory in _iter_path_dirs():
        try:
            for entry in directory.iterdir():
                try:
                    mode = entry.stat().st_mode
                except OSError:
                    continue
                if not entry.is_file():
                    continue
                if os.name == "nt":
                    if entry.suffix.lower() not in pathext:
                        continue
                elif not (mode & stat.S_IXUSR):
                    continue
                if entry.name in seen:
                    continue
                if entry.name not in seen:
                    seen.add(entry.name)
                    tools.append(entry.name)
        except OSError:
            continue
    return sorted(tools)


def snapshot_path_state() -> dict[str, float]:
    snapshot: dict[str, float] = {}
    for directory in _iter_path_dirs():
        try:
            snapshot[str(directory)] = directory.stat().st_mtime
        except OSError:
            continue
    return snapshot
