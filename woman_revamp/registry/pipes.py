"""Pre-composed pipe templates for common multi-command patterns."""

from __future__ import annotations

import re

# Each tuple: (trigger_regex, label, composed_template_with_slots)
PIPE_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"\bfind\b.{0,30}\bdelete\b|\bdelete\b.{0,30}\bfind\b", re.I),
        "find+delete",
        "find {path} -name '{pattern}' -delete",
    ),
    (
        re.compile(r"\bcount\b.{0,20}\blines?\b|\blines?\b.{0,20}\bcount\b", re.I),
        "count+lines",
        "find {path} -name '{pattern}' | xargs wc -l",
    ),
    (
        re.compile(r"\blargest?\b.{0,20}\bfiles?\b", re.I),
        "disk+sort",
        "du -sh {path}/* | sort -rh | head -{lines}",
    ),
    (
        re.compile(r"\bgrep\b.{0,20}\bcount\b|\bcount\b.{0,20}\bgrep\b", re.I),
        "grep+count",
        "grep -rc '{pattern}' {path}",
    ),
    (
        re.compile(r"\bfind\b.{0,20}\bcompress\b|\bcompress\b.{0,20}\bfind\b", re.I),
        "find+compress",
        "find {path} -name '{pattern}' | tar -czf {archive} -T -",
    ),
    (
        re.compile(r"\bsort\b.{0,20}\buniq\b|\bunique\b", re.I),
        "sort+unique",
        "sort {file} | uniq",
    ),
    (
        re.compile(r"\btop\s+\d+.{0,20}\bprocess", re.I),
        "top+process",
        "ps aux --sort=-{sort_field} | head -{lines}",
    ),
]
