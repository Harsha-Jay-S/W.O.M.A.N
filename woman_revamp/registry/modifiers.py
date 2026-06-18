"""Modifier-word to CLI-flag mapping for query slot filling."""

from __future__ import annotations

MODIFIER_FLAGS: dict[str, str] = {
    "recursively":      "-r",
    "recursive":        "-r",
    "silently":         "2>/dev/null",
    "quietly":          "-q",
    "quiet":            "-q",
    "force":            "-f",
    "forced":           "-f",
    "verbose":          "-v",
    "verbosely":        "-v",
    "case-insensitive": "-i",
    "insensitive":      "-i",
    "human-readable":   "-h",
    "humanreadable":    "-h",
    "dry-run":          "--dry-run",
    "preview":          "-n",
    "sorted":           "--sort",
    "by-size":          "--sort=size",
    "by-time":          "--sort=time",
    "by-date":          "--sort=time",
    "hidden":           "-a",
    "global":           "-g",
}

# Commands that accept an optional {flags} slot
FLAGS_AWARE_COMMANDS: frozenset[str] = frozenset({
    "find", "ls", "grep", "cp", "rm", "rsync", "sed", "awk", "sort", "tar",
})
