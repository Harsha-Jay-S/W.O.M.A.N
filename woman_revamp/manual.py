"""Man page viewer for woman."""

from __future__ import annotations

import shutil
import subprocess
import sys


def show_man_page(command_name: str) -> int:
    """Open the man page for a command, fall back to --help."""
    if shutil.which("man"):
        probe = subprocess.run(["man", command_name], capture_output=True)
        if probe.returncode == 0:
            return subprocess.run(["man", command_name]).returncode
    print(f"No man page found for '{command_name}'. Trying --help...", file=sys.stderr)
    try:
        return subprocess.run([command_name, "--help"]).returncode
    except FileNotFoundError:
        print(f"Command '{command_name}' not found.", file=sys.stderr)
        return 1
