"""Tests for fallback behavior of ui helpers when questionary is unavailable."""

import builtins

from woman_revamp.ui import Choice, prompt_choice, prompt_text


def _make_import_raiser():
    original_import = builtins.__import__

    def raiser(name, *args, **kwargs):
        if name == "questionary":
            raise ImportError("questionary not available")
        return original_import(name, *args, **kwargs)

    return raiser


def _patch_import_and_input(monkeypatch, input_values=None):
    monkeypatch.setattr(builtins, "__import__", _make_import_raiser())
    if input_values is not None:
        it = iter(input_values)
        monkeypatch.setattr(builtins, "input", lambda prompt="": next(it))


class TestPromptTextFallback:
    def test_prompt_text_fallback_importerror_empty_returns_default(self, monkeypatch):
        _patch_import_and_input(monkeypatch, [""])
        assert prompt_text("Name?", default="Alice") == "Alice"

    def test_prompt_text_fallback_importerror_nonempty(self, monkeypatch):
        _patch_import_and_input(monkeypatch, ["hello"])
        assert prompt_text("Name?", default="Alice") == "hello"


class TestPromptChoiceFallback:
    def test_prompt_choice_fallback_empty_returns_default(self, monkeypatch):
        choices = [Choice(key="a", label="Alpha"), Choice(key="b", label="Beta")]
        _patch_import_and_input(monkeypatch, [""])
        assert prompt_choice("Pick", choices, default="b") == "b"

    def test_prompt_choice_fallback_by_number(self, monkeypatch):
        choices = [Choice(key="a", label="Alpha"), Choice(key="b", label="Beta")]
        _patch_import_and_input(monkeypatch, ["2"])
        assert prompt_choice("Pick", choices, default="a") == "b"

    def test_prompt_choice_fallback_by_key(self, monkeypatch):
        choices = [Choice(key="a", label="Alpha"), Choice(key="b", label="Beta")]
        _patch_import_and_input(monkeypatch, ["b"])
        assert prompt_choice("Pick", choices, default="a") == "b"

    def test_prompt_choice_fallback_retry_then_valid(self, monkeypatch):
        choices = [
            Choice(key="x", label="Xray"),
            Choice(key="y", label="Yankee"),
            Choice(key="z", label="Zulu"),
        ]
        _patch_import_and_input(monkeypatch, ["bad", "3"])
        assert prompt_choice("Pick", choices, default="x") == "z"

    def test_prompt_choice_fallback_invalid_after_retries(self, monkeypatch):
        choices = [
            Choice(key="a", label="Alpha"),
            Choice(key="b", label="Beta"),
            Choice(key="c", label="Charlie"),
        ]
        _patch_import_and_input(monkeypatch, ["bad", "also_bad", "x"])
        assert prompt_choice("Pick", choices, default="b") == "b"
