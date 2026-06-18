"""Feature helpers for the command reranker."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

TOKEN_RE = re.compile(r"[A-Za-z0-9_./:-]+")


@dataclass(frozen=True)
class CandidateFeatures:
    query: str
    candidate_command: str
    recent_history: str
    combined_text: str
    os: str
    heuristic_rank: int
    token_overlap_ratio: float
    query_length: int
    candidate_length: int
    has_pipe: int
    has_sudo: int
    has_git: int
    has_docker: int
    has_python: int
    is_destructive: int


def normalize_text(text: object) -> str:
    if text is None:
        return ""
    value = str(text).strip().lower()
    return re.sub(r"\s+", " ", value)


def tokenize_text(text: object) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(normalize_text(text))]


def overlap_ratio(query_text: object, candidate_text: object) -> float:
    query_tokens = set(tokenize_text(query_text))
    candidate_tokens = set(tokenize_text(candidate_text))
    if not query_tokens:
        return 0.0
    return len(query_tokens & candidate_tokens) / len(query_tokens)


def contains_any(text_value: object, patterns: Iterable[str]) -> int:
    text = normalize_text(text_value)
    return int(any(pattern in text for pattern in patterns))


def is_destructive_command(command_text: object) -> int:
    from .safety import is_destructive_command as _safety_check
    return _safety_check(command_text)


def build_inference_frame(
    query: str,
    os_name: str,
    recent_history: Sequence[str] | str,
    candidates: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    if isinstance(recent_history, str):
        history_text = recent_history
    else:
        history_text = " || ".join(str(item) for item in recent_history[-5:])

    rows: list[dict[str, object]] = []
    for index, candidate in enumerate(candidates, start=1):
        command = normalize_text(
            candidate.get("rendered")
            or candidate.get("command")
            or candidate.get("candidate_command")
        )
        row = {
            "query": normalize_text(query),
            "candidate_command": command,
            "recent_history": normalize_text(history_text),
            "combined_text": normalize_text(query) + " [SEP] " + command,
            "os": normalize_text(os_name),
            "heuristic_rank": int(candidate.get("heuristic_rank", index)),
            "token_overlap_ratio": overlap_ratio(query, command),
            "query_length": len(tokenize_text(query)),
            "candidate_length": len(tokenize_text(command)),
            "has_pipe": int("|" in command),
            "has_sudo": contains_any(command, ["sudo"]),
            "has_git": contains_any(command, ["git"]),
            "has_docker": contains_any(command, ["docker"]),
            "has_python": contains_any(command, ["python", "pip"]),
            "is_destructive": is_destructive_command(command),
        }
        rows.append(row)
    return rows
