"""Extension-to-runner mapping for runnable script files."""

from __future__ import annotations

RUNNERS: dict[str, str] = {
    ".py":  "python",
    ".sh":  "bash",
    ".zsh": "zsh",
    ".js":  "node",
    ".ts":  "npx ts-node",
    ".rb":  "ruby",
    ".pl":  "perl",
    ".php": "php",
    ".lua": "lua",
    ".r":   "Rscript",
    ".go":  "go run",
    ".rs":  "cargo run",
}

RUNNABLE_EXTENSIONS: frozenset[str] = frozenset(RUNNERS)
