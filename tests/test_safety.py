"""Tests for the safety scoring engine."""

from woman_revamp.ml.safety import (
    AUTO_THRESHOLD,
    CONFIRM_THRESHOLD,
    DANGER_PATTERNS,
    DESTRUCTIVE_PENALTY,
    adjust_score,
    calculate_danger_score,
    decide_action,
    is_destructive_command,
    rerank_with_safety,
)


def test_danger_patterns_are_typed():
    assert isinstance(DANGER_PATTERNS, list)
    assert len(DANGER_PATTERNS) >= 5
    for pattern, penalty, reason in DANGER_PATTERNS:
        assert isinstance(pattern, str)
        assert isinstance(penalty, float)
        assert 0.0 < penalty <= 1.0
        assert isinstance(reason, str)


def test_calculate_danger_score_safe_command():
    score, reasons = calculate_danger_score("ls -la")
    assert score == 0.0
    assert reasons == []


def test_calculate_danger_score_rm():
    score, reasons = calculate_danger_score("rm file.txt")
    assert score == 0.40
    assert "Permanent file deletion" in reasons


def test_calculate_danger_score_rm_rf():
    score, reasons = calculate_danger_score("rm -rf /var/log")
    assert score == 0.85
    assert any("Recursive force delete" in r for r in reasons)


def test_calculate_danger_score_rm_rf_root():
    score, reasons = calculate_danger_score("rm -rf /")
    assert score == 0.95
    assert any("Deleting root filesystem" in r for r in reasons)
    assert any("Recursive force delete" in r for r in reasons)


def test_calculate_danger_score_dd():
    score, reasons = calculate_danger_score("dd if=/dev/zero of=/dev/sda bs=4M")
    assert score == 0.90
    assert any("Low-level disk write" in r for r in reasons)


def test_calculate_danger_score_mkfs():
    score, reasons = calculate_danger_score("mkfs.ext4 /dev/sdb1")
    assert score == 0.95
    assert any("Filesystem creation" in r for r in reasons)


def test_calculate_danger_score_shutdown():
    score, reasons = calculate_danger_score("shutdown -h now")
    assert score == 0.70
    assert "System shutdown" in reasons


def test_calculate_danger_score_reboot():
    score, reasons = calculate_danger_score("reboot")
    assert score == 0.60
    assert "System reboot" in reasons


def test_is_destructive_command_rm():
    assert is_destructive_command("rm file.txt") == 1


def test_is_destructive_command_safe():
    assert is_destructive_command("ls -la") == 0


def test_is_destructive_command_empty():
    assert is_destructive_command("") == 0


def test_is_destructive_command_none():
    assert is_destructive_command(None) == 0


def test_adjust_score_destructive_penalty():
    candidate = {"score": 0.9, "rendered": "rm -rf /"}
    adjusted = adjust_score(candidate)
    assert adjusted < 0.9
    assert adjusted >= 0.9 - DESTRUCTIVE_PENALTY


def test_adjust_score_safe_no_penalty():
    candidate = {"score": 0.9, "rendered": "ls -la"}
    adjusted = adjust_score(candidate)
    assert adjusted == 0.9


def test_adjust_score_clamps_bounds():
    candidate = {"score": 0.0, "rendered": "rm -rf /"}
    adjusted = adjust_score(candidate)
    assert adjusted == 0.0


def test_decide_action_auto_accept():
    ranked = rerank_with_safety([
        {"rendered": "ls -la", "score": 0.95, "heuristic_rank": 1},
    ])
    decision = decide_action(ranked)
    assert decision["action"] == "auto_accept"


def test_decide_action_confirm_for_danger():
    ranked = rerank_with_safety([
        {"rendered": "rm -rf /", "score": 0.95, "heuristic_rank": 1},
    ])
    decision = decide_action(ranked)
    assert decision["action"] == "confirm"
    assert decision.get("danger_score", 0) >= 0.85


def test_decide_action_confirm_normal():
    # score 0.7, non-destructive, so no penalty — triggers confirm (0.60 <= 0.70 < 0.85)
    ranked = rerank_with_safety([
        {"rendered": "ls -la", "score": 0.7, "heuristic_rank": 1},
    ])
    decision = decide_action(ranked)
    assert decision["action"] == "confirm"


def test_decide_action_show_choices():
    ranked = rerank_with_safety([
        {"rendered": "ls", "score": 0.3, "heuristic_rank": 1},
    ])
    decision = decide_action(ranked)
    assert decision["action"] == "show_choices"


def test_decide_action_no_match():
    decision = decide_action([])
    assert decision["action"] == "no_match"


def test_rerank_with_safety_injects_danger_fields():
    candidates = [
        {"rendered": "rm -rf /", "score": 0.9, "heuristic_rank": 1},
        {"rendered": "ls", "score": 0.8, "heuristic_rank": 2},
    ]
    result = rerank_with_safety(candidates)
    for item in result:
        assert "danger_score" in item
        assert "danger_reasons" in item
        assert "ml_score" in item


def test_rerank_with_safety_sorts_by_score():
    candidates = [
        {"rendered": "ls", "score": 0.5, "heuristic_rank": 2},
        {"rendered": "pwd", "score": 0.9, "heuristic_rank": 1},
    ]
    result = rerank_with_safety(candidates)
    assert result[0]["rendered"] == "pwd"
    assert result[1]["rendered"] == "ls"


def test_constants_are_correct():
    assert AUTO_THRESHOLD == 0.85
    assert CONFIRM_THRESHOLD == 0.60
    assert DESTRUCTIVE_PENALTY == 0.35
