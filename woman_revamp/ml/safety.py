"""Safety guardrails for reranked commands."""

from __future__ import annotations

import os
import re
from typing import Iterable, Mapping

DANGER_PATTERNS: list[tuple[str, float, str]] = [
    (r"\brm\s+-rf\s+/\s*$", 0.95, "Deleting root filesystem — extreme danger"),
    (r"\brm\s+-rf\b", 0.85, "Recursive force delete — irreversible"),
    (r"\brm\b", 0.40, "Permanent file deletion"),
    (r"\bdd\b", 0.90, "Low-level disk write — can destroy data"),
    (r"\bmkfs\b", 0.95, "Filesystem creation — destructive"),
    (r"\bshutdown\b", 0.70, "System shutdown"),
    (r"\breboot\b", 0.60, "System reboot"),
    (r"\bformat\b", 0.90, "Format operation — destructive"),
    (r"\bmke2fs\b", 0.95, "Filesystem creation — destructive"),
    (r"\bparted\b.*\brm\b", 0.95, "Partition deletion — data loss"),
    (r"\bfdisk\b", 0.80, "Disk partitioning — high risk"),
    (r">\s*/dev/\w+", 0.85, "Writing to device directly — dangerous"),
    (r"\|\s*sudo\b", 0.50, "Piped to sudo — elevated risk"),
]

AUTO_THRESHOLD = 0.85
CONFIRM_THRESHOLD = 0.60
DESTRUCTIVE_PENALTY = 0.35


def calculate_danger_score(command: str) -> tuple[float, list[str]]:
    """Return (max_danger_score, list_of_reasons) for a command string."""
    if os.environ.get("WOMAN_SAFETY_OFF") == "1":
        return 0.0, []
    reasons: list[str] = []
    score = 0.0
    for pattern, penalty, reason in DANGER_PATTERNS:
        if re.search(pattern, command.strip()):
            if penalty > score:
                score = penalty
            if reason not in reasons:
                reasons.append(reason)
    return min(score, 1.0), reasons


def is_destructive_command(command_text: object) -> int:
    """Check if a command matches any destructive pattern."""
    text = str(command_text).strip().lower() if command_text else ""
    return int(any(re.search(pattern, text) for pattern, _, _ in DANGER_PATTERNS))


def _extract_score(candidate: Mapping[str, object]) -> float:
    value = candidate.get("ml_score", candidate.get("score", 0.0))
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def adjust_score(candidate: Mapping[str, object]) -> float:
    score = _extract_score(candidate)
    command = str(
        candidate.get("rendered")
        or candidate.get("command")
        or candidate.get("candidate_command")
        or ""
    )
    if is_destructive_command(command):
        score -= DESTRUCTIVE_PENALTY
    return max(0.0, min(1.0, score))


def rerank_with_safety(
    candidates: Iterable[Mapping[str, object]]
) -> list[dict[str, object]]:
    adjusted: list[dict[str, object]] = []
    for candidate in candidates:
        item = dict(candidate)
        item["ml_score"] = adjust_score(item)
        command = str(
            item.get("rendered")
            or item.get("command")
            or item.get("candidate_command")
            or ""
        )
        danger_score, reasons = calculate_danger_score(command)
        item["danger_score"] = danger_score
        item["danger_reasons"] = reasons
        adjusted.append(item)
    adjusted.sort(
        key=lambda item: (
            item.get("ml_score", 0.0),
            -int(item.get("heuristic_rank", 999)),
        ),
        reverse=True,
    )
    return adjusted


def decide_action(candidates: Iterable[Mapping[str, object]], *, already_ranked: bool = False) -> dict[str, object]:
    ranked = list(candidates) if already_ranked else rerank_with_safety(candidates)
    if not ranked:
        return {"action": "no_match"}
    top = ranked[0]
    score = float(top.get("ml_score", 0.0))
    danger_score = float(top.get("danger_score", 0.0))
    cmd = top.get("rendered") or top.get("command") or top.get("candidate_command") or ""
    if danger_score >= 0.85:
        return {
            "action": "confirm",
            "command": cmd,
            "score": score,
            "danger_score": danger_score,
            "danger_reasons": top.get("danger_reasons", []),
        }
    if score >= AUTO_THRESHOLD:
        return {
            "action": "auto_accept",
            "command": cmd,
            "score": score,
            "danger_score": danger_score,
            "danger_reasons": top.get("danger_reasons", []),
        }
    if score >= CONFIRM_THRESHOLD:
        return {
            "action": "confirm",
            "command": cmd,
            "score": score,
            "danger_score": danger_score,
            "danger_reasons": top.get("danger_reasons", []),
        }
    return {"action": "show_choices", "candidates": ranked}
