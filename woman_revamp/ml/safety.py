"""Safety guardrails for reranked commands."""

from __future__ import annotations

from typing import Iterable, Mapping

from .features import is_destructive_command

AUTO_THRESHOLD = 0.85
CONFIRM_THRESHOLD = 0.60
DESTRUCTIVE_PENALTY = 0.35


def _extract_score(candidate: Mapping[str, object]) -> float:
    value = candidate.get("ml_score", candidate.get("score", 0.0))
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def adjust_score(candidate: Mapping[str, object]) -> float:
    score = _extract_score(candidate)
    if candidate.get("is_destructive") or is_destructive_command(candidate.get("rendered") or candidate.get("command") or candidate.get("candidate_command")):
        score -= DESTRUCTIVE_PENALTY
    return max(0.0, min(1.0, score))


def rerank_with_safety(candidates: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    adjusted: list[dict[str, object]] = []
    for candidate in candidates:
        item = dict(candidate)
        item["ml_score"] = adjust_score(item)
        adjusted.append(item)
    adjusted.sort(key=lambda item: (item.get("ml_score", 0.0), -int(item.get("heuristic_rank", 999))), reverse=True)
    return adjusted


def decide_action(candidates: Iterable[Mapping[str, object]]) -> dict[str, object]:
    ranked = rerank_with_safety(candidates)
    if not ranked:
        return {"action": "no_match"}
    top = ranked[0]
    score = float(top.get("ml_score", 0.0))
    if score >= AUTO_THRESHOLD:
        return {"action": "auto_accept", "command": top.get("rendered") or top.get("command"), "score": score}
    if score >= CONFIRM_THRESHOLD:
        return {"action": "confirm", "command": top.get("rendered") or top.get("command"), "score": score}
    return {"action": "show_choices", "candidates": ranked}
