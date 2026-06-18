"""Tests for CLI parser and subcommand dispatch."""

import argparse
import sys

import pytest

from woman_revamp.cli import (
    _SUBCOMMANDS,
    _handle_subcommand,
    build_parser,
    build_subcommand_parser,
    main,
)


class TestBuildParser:
    """Tests for the legacy (flat) argument parser."""

    def test_parser_accepts_query(self):
        parser = build_parser()
        ns = parser.parse_args(["find", "files"])
        assert ns.query == ["find", "files"]

    def test_parser_empty_query(self):
        parser = build_parser()
        ns = parser.parse_args([])
        assert ns.query == []

    def test_parser_has_dry_run(self):
        parser = build_parser()
        ns = parser.parse_args(["--dry-run", "list", "files"])
        assert ns.dry_run is True
        assert ns.query == ["list", "files"]

    def test_parser_has_explain(self):
        parser = build_parser()
        ns = parser.parse_args(["--explain", "find", "files"])
        assert ns.explain is True

    def test_parser_has_manual(self):
        parser = build_parser()
        ns = parser.parse_args(["--manual", "find", "files"])
        assert ns.manual is True

    def test_parser_has_json(self):
        parser = build_parser()
        ns = parser.parse_args(["--json", "find", "files"])
        assert ns.json is True

    def test_parser_has_list(self):
        parser = build_parser()
        ns = parser.parse_args(["--list"])
        assert ns.list is True

    def test_parser_has_config(self):
        parser = build_parser()
        ns = parser.parse_args(["--config"])
        assert ns.config is True

    def test_parser_default_top(self):
        parser = build_parser()
        ns = parser.parse_args(["find files"])
        assert ns.top == 5

    def test_parser_custom_top(self):
        parser = build_parser()
        ns = parser.parse_args(["--top", "3", "find files"])
        assert ns.top == 3


class TestBuildSubcommandParser:

    def test_subcommand_search(self):
        parser = build_subcommand_parser()
        ns = parser.parse_args(["search", "find", "files"])
        assert ns.subcommand == "search"
        assert ns.query == ["find", "files"]

    def test_subcommand_search_alias(self):
        parser = build_subcommand_parser()
        ns = parser.parse_args(["s", "find", "files"])
        assert ns.subcommand == "s"

    def test_subcommand_list(self):
        parser = build_subcommand_parser()
        ns = parser.parse_args(["list"])
        assert ns.subcommand == "list"

    def test_subcommand_explain(self):
        parser = build_subcommand_parser()
        ns = parser.parse_args(["explain", "find", "files"])
        assert ns.subcommand == "explain"

    def test_subcommand_manual(self):
        parser = build_subcommand_parser()
        ns = parser.parse_args(["manual", "find"])
        assert ns.subcommand == "manual"

    def test_subcommand_man_alias(self):
        parser = build_subcommand_parser()
        ns = parser.parse_args(["man", "ls"])
        assert ns.subcommand == "man"

    def test_subcommand_config(self):
        parser = build_subcommand_parser()
        ns = parser.parse_args(["config"])
        assert ns.subcommand == "config"

    def test_subcommand_index_refresh(self):
        parser = build_subcommand_parser()
        ns = parser.parse_args(["index", "refresh"])
        assert ns.subcommand == "index"
        assert ns.index_action == "refresh"

    def test_subcommand_index_add(self):
        parser = build_subcommand_parser()
        ns = parser.parse_args(["index", "add", "find"])
        assert ns.subcommand == "index"
        assert ns.index_action == "add"
        assert ns.tool == "find"

    def test_subcommand_shell_integration(self):
        parser = build_subcommand_parser()
        ns = parser.parse_args(["shell-integration", "zsh"])
        assert ns.subcommand == "shell-integration"
        assert ns.shell == "zsh"

    def test_subcommand_requires_subcommand(self):
        parser = build_subcommand_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_subcommand_search_accepts_dry_run(self):
        parser = build_subcommand_parser()
        ns = parser.parse_args(["search", "--dry-run", "find", "files"])
        assert ns.dry_run is True


class TestSubcommandsConstant:

    def test_all_subcommands_listed(self):
        expected = {
            "search", "s", "list", "explain", "manual", "man", "config", "index",
            "shell-integration", "history", "redo", "why",
        }
        assert _SUBCOMMANDS == expected

    def test_subcommand_set_is_exhaustive(self):
        from argparse import _SubParsersAction
        parser = build_subcommand_parser()
        seen: set[str] = set()
        for action in parser._subparsers._group_actions:
            if isinstance(action, _SubParsersAction):
                for name, sp in action.choices.items():
                    seen.add(name)
        assert seen == _SUBCOMMANDS, f"Subcommand mismatch: extra={seen - _SUBCOMMANDS}, missing={_SUBCOMMANDS - seen}"


class TestHandleSubcommand:

    def test_handle_config(self, monkeypatch):
        ns = argparse.Namespace(subcommand="config")
        monkeypatch.setattr("woman_revamp.cli.run_setup", lambda: None)
        monkeypatch.setattr("woman_revamp.cli.auto_detect_lean_mode", lambda: True)
        assert _handle_subcommand(ns) == 0

    def test_shell_integration_bash(self, capsys):
        ns = argparse.Namespace(subcommand="shell-integration", shell="bash")
        rc = _handle_subcommand(ns)
        captured = capsys.readouterr()
        assert rc == 0
        assert "W.O.M.A.N" in captured.out

    def test_why_subcommand_returns_zero(self, capsys):
        ns = argparse.Namespace(subcommand="why", query=["find", "files"], os_name=None)
        rc = _handle_subcommand(ns)
        assert rc == 0

    def test_history_subcommand_empty(self, tmp_path, monkeypatch):
        import woman_revamp.query_history as _qh
        monkeypatch.setattr(_qh, "HISTORY_FILE", tmp_path / "h.json")
        ns = argparse.Namespace(subcommand="history", count=10)
        rc = _handle_subcommand(ns)
        assert rc == 0

    def test_redo_subcommand_no_history(self, tmp_path, monkeypatch):
        import woman_revamp.query_history as _qh
        monkeypatch.setattr(_qh, "HISTORY_FILE", tmp_path / "h.json")
        ns = argparse.Namespace(subcommand="redo")
        rc = _handle_subcommand(ns)
        assert rc == 1


# ── Entrypoint routing tests (the "Queen" phase fix) ──────────────────────────

class TestMainHelpInterface:
    """--help should surface the subcommand interface, not the legacy flat flags."""

    def test_help_flag_prog_name_is_woman_not_woman_revamp(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "woman-revamp" not in out

    def test_help_flag_lists_search_subcommand(self, capsys):
        with pytest.raises(SystemExit):
            main(["--help"])
        out = capsys.readouterr().out
        assert "search" in out

    def test_help_flag_lists_explain_subcommand(self, capsys):
        """'explain' must appear as a subcommand, not just the --explain flag name."""
        with pytest.raises(SystemExit):
            main(["--help"])
        out = capsys.readouterr().out
        # Subcommand parsers list choices like "{search,s,list,explain,...}"
        # Legacy parser shows "--explain" but NOT "explain" as a standalone word
        assert "explain" in out and "--explain" not in out

    def test_help_flag_lists_history_subcommand(self, capsys):
        """'history' must appear as a listed subcommand, not in a flag description."""
        with pytest.raises(SystemExit):
            main(["--help"])
        out = capsys.readouterr().out
        # Legacy help has "history" only inside "--context ... or history" description.
        # Subcommand help lists it as a first-class subcommand name.
        assert "history" in out and "--context" not in out


class TestMainNoArgs:
    """woman with no args should print usage, not silently do nothing."""

    def test_no_args_prints_usage_containing_woman(self, capsys):
        main([])
        out = capsys.readouterr().out
        assert "woman" in out

    def test_no_args_returns_0(self):
        rc = main([])
        assert rc == 0


class TestMainLegacyBackwardsCompat:
    """Old flags must keep working after the routing refactor."""

    def _setup(self, monkeypatch, tmp_path):
        import woman_revamp.cli as _cli
        monkeypatch.setattr(_cli, "CONFIG_FILE", tmp_path / "config.yaml")
        monkeypatch.setattr(_cli, "run_setup", lambda: None)

    def test_legacy_list_flag_returns_0(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        assert main(["--list"]) == 0

    def test_legacy_list_flag_with_os_returns_0(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        assert main(["--list", "--os", "linux"]) == 0

    def test_legacy_json_flag_returns_0(self, monkeypatch, tmp_path, capsys):
        self._setup(monkeypatch, tmp_path)
        rc = main(["--json", "find", "files"])
        assert rc == 0
        out = capsys.readouterr().out
        assert out.strip().startswith("[")

    def test_legacy_dry_run_flag_returns_0(self, monkeypatch, tmp_path, capsys):
        self._setup(monkeypatch, tmp_path)
        rc = main(["--dry-run", "list", "files"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Dry run" in out

    def test_legacy_refresh_index_flag_returns_0(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        monkeypatch.setattr("woman_revamp.cli.refresh_registry_cache", lambda **kw: None)
        assert main(["--refresh-index"]) == 0

    def test_legacy_index_tool_flag_returns_0(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        monkeypatch.setattr("woman_revamp.cli.index_one", lambda tool, **kw: None)
        assert main(["--index-tool", "find"]) == 0


class TestClipboard:

    def test_copy_to_clipboard_returns_bool(self, monkeypatch):
        from woman_revamp.cli import _copy_to_clipboard
        # Monkeypatch subprocess.run to simulate no clipboard tool
        import shutil as _shutil
        monkeypatch.setattr(_shutil, "which", lambda _: None)
        result = _copy_to_clipboard("ls -la")
        assert isinstance(result, bool)
        assert result is False

    def test_copy_to_clipboard_with_mock_tool(self, monkeypatch):
        from woman_revamp.cli import _copy_to_clipboard
        import shutil as _shutil
        import subprocess as _sub

        def fake_which(cmd):
            return "/usr/bin/xclip" if cmd == "xclip" else None

        def fake_run(args, **kwargs):
            class FakeProc:
                returncode = 0
            return FakeProc()

        monkeypatch.setattr(_shutil, "which", fake_which)
        monkeypatch.setattr(_sub, "run", fake_run)
        import sys
        monkeypatch.setattr(sys, "platform", "linux")
        result = _copy_to_clipboard("ls -la")
        assert result is True
