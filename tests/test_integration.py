"""Integration tests: context-aware queries with temp-dir fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from woman_revamp.engine import rank_candidates


class TestRunShortcut:

    def test_run_single_python_script(self, tmp_path: Path) -> None:
        script = tmp_path / "hello.py"
        script.write_text("print('hello')")
        result = rank_candidates(
            "run the script",
            active_files=[script],
            os_info="linux",
            limit=1,
        )
        assert result, "Should return at least one result"
        assert result[0]["rendered"] == "python hello.py"
        assert result[0]["source"] == "shortcut"

    def test_run_single_bash_script(self, tmp_path: Path) -> None:
        script = tmp_path / "deploy.sh"
        script.write_text("#!/bin/bash\necho hi")
        result = rank_candidates(
            "run the script",
            active_files=[script],
            os_info="linux",
            limit=1,
        )
        assert result[0]["rendered"] == "bash deploy.sh"
        assert result[0]["source"] == "shortcut"

    def test_run_ambiguous_scripts_returns_multiple(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text("")
        (tmp_path / "server.js").write_text("")
        files = list(tmp_path.iterdir())
        result = rank_candidates(
            "run the script",
            active_files=files,
            os_info="linux",
            limit=5,
        )
        rendered = [r["rendered"] for r in result]
        assert any("python" in r for r in rendered)
        assert any("node" in r for r in rendered)
        assert all(r["source"] == "shortcut" for r in result)

    def test_no_runnable_files_falls_through(self, tmp_path: Path) -> None:
        (tmp_path / "config.yaml").write_text("")
        result = rank_candidates(
            "run the script",
            active_files=list(tmp_path.iterdir()),
            os_info="linux",
            limit=1,
        )
        # Falls through to normal scoring; must not produce shortcut
        if result:
            assert result[0].get("source") != "shortcut"

    def test_run_intent_triggers_shortcut(self, tmp_path: Path) -> None:
        script = tmp_path / "test.py"
        script.write_text("")
        result = rank_candidates(
            "run the file",
            active_files=[script],
            os_info="linux",
            limit=1,
        )
        assert result
        assert result[0]["source"] == "shortcut"
        assert "python" in result[0]["rendered"]


class TestProjectSignals:

    def test_python_project_boosts_python(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("")
        from woman_revamp.context import get_project_signals
        signals = get_project_signals(tmp_path)
        assert signals["python"] is True
        # python command should score higher with signals
        with_signals = rank_candidates(
            "run python script", os_info="linux", limit=3, project_signals=signals
        )
        without_signals = rank_candidates(
            "run python script", os_info="linux", limit=3
        )
        py_with = next((r for r in with_signals if r["command"] == "python"), None)
        py_without = next((r for r in without_signals if r["command"] == "python"), None)
        if py_with and py_without:
            assert py_with["score"] >= py_without["score"]

    def test_git_project_boosts_git(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        from woman_revamp.context import get_project_signals
        signals = get_project_signals(tmp_path)
        assert signals["git"] is True
        results = rank_candidates(
            "show repository log", os_info="linux", limit=3, project_signals=signals
        )
        # git should appear in top results
        names = [r["command"] for r in results]
        assert "git" in names


class TestPipeComposition:

    def test_find_delete_pattern(self) -> None:
        results = rank_candidates(
            "find and delete tmp files", os_info="linux", limit=3
        )
        assert results
        top = results[0]
        assert top["source"] == "pipe_shortcut"
        assert "-delete" in top["rendered"]

    def test_sort_unique_pattern(self) -> None:
        results = rank_candidates(
            "sort and unique the file", os_info="linux", limit=3
        )
        assert results
        top = results[0]
        assert top["source"] == "pipe_shortcut"
        assert "uniq" in top["rendered"]


class TestNegation:

    def test_negated_command_scores_low(self) -> None:
        with_neg = rank_candidates("not rm these files", os_info="linux", limit=5)
        without_neg = rank_candidates("delete these files", os_info="linux", limit=5)
        rm_with = next((r for r in with_neg if r["command"] == "rm"), None)
        rm_without = next((r for r in without_neg if r["command"] == "rm"), None)
        if rm_with and rm_without:
            assert rm_with["score"] < rm_without["score"]


class TestModifierFlags:

    def test_recursive_modifier_fills_flags_slot(self) -> None:
        results = rank_candidates(
            "copy files recursively", os_info="linux", limit=3
        )
        assert results
        rendered_all = " ".join(r.get("rendered", "") for r in results)
        # Modifier "recursively" → -r appended to any FLAGS_AWARE_COMMANDS result
        assert "-r" in rendered_all, f"Expected -r in rendered output, got: {rendered_all}"
