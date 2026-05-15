"""Runtime dependency bootstrap for woman_revamp."""

from __future__ import annotations

import os
import subprocess
import sys
from importlib.util import find_spec
from shutil import which


REQUIRED_UI_PACKAGES = ("rich", "questionary")


def missing_ui_dependencies() -> list[str]:
    missing: list[str] = []
    for package in REQUIRED_UI_PACKAGES:
        if find_spec(package) is None:
            missing.append(package)
    return missing


def prompt_install_missing(missing: list[str]) -> bool:
    if not missing:
        return True
    print("woman_revamp needs these missing dependencies:")
    print("  " + ", ".join(missing))
    answer = input("Install them now and continue? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        return False
    if which("uv"):
        cmd = ["uv", "pip", "install", *missing]
    else:
        cmd = [sys.executable, "-m", "pip", "install", *missing]
    completed = subprocess.run(cmd, check=False)
    return completed.returncode == 0


def ensure_runtime_dependencies() -> None:
    missing = missing_ui_dependencies()
    if not missing:
        return
    if not prompt_install_missing(missing):
        raise SystemExit(1)
    os.execv(sys.executable, [sys.executable, *sys.argv])
