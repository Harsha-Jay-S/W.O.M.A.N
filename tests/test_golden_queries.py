"""Golden regression corpus: real queries → invariants on finalized output.

Every edge case the tool gets wrong should become a row here so it can never
silently regress.  Assertions are on *properties* (scope, safety, portability),
not exact strings, so they survive harmless wording changes.
"""

from __future__ import annotations

import os

import pytest

from woman_revamp.engine import extract_intent, rank_candidates
from woman_revamp.finalize import _risk_level, finalize_command

GOLDEN_QUERIES = [
    "zip all available folders in this directory",
    "zip all folders into one archive",
    "compress this directory",
    "find all python files modified today",
    "list running processes",
    "show disk usage",
]


def _finalize_top(query: str, cwd: str):
    candidates = rank_candidates(query, os_info="linux", limit=1)
    command = ""
    if candidates:
        command = str(candidates[0].get("rendered") or candidates[0].get("command") or "")
    return finalize_command(query, command, list(extract_intent(query)), cwd=cwd)


@pytest.mark.parametrize("query", GOLDEN_QUERIES)
def test_finalize_never_leaks_absolute_cwd(query, tmp_path):
    result = _finalize_top(query, str(tmp_path))
    assert os.path.abspath(str(tmp_path)) not in result.command


@pytest.mark.parametrize("query", GOLDEN_QUERIES)
def test_finalize_never_emits_rm_rf_root(query, tmp_path):
    assert "rm -rf /" not in result_command(query, tmp_path)


def result_command(query, tmp_path):
    return _finalize_top(query, str(tmp_path)).command


@pytest.mark.parametrize("query", GOLDEN_QUERIES)
def test_risk_level_consistent_with_score(query, tmp_path):
    result = _finalize_top(query, str(tmp_path))
    assert result.risk_level == _risk_level(result.risk_score)


@pytest.mark.parametrize("query", GOLDEN_QUERIES)
def test_restatement_always_present(query, tmp_path):
    assert _finalize_top(query, str(tmp_path)).restatement.strip() != ""


def test_zip_all_folders_bug_is_fixed(tmp_path):
    """The original reported bug: 'zip all folders' must become a per-folder loop."""
    result = _finalize_top("zip all available folders in this directory", str(tmp_path))
    assert "for d in */" in result.command
    assert 'zip -r "${d%/}.zip" "$d"' in result.command
