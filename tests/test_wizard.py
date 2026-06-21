"""Tests for wizard AI provider configuration — custom endpoints and model names."""

import pytest

from woman_revamp.config import WomanConfig


def _run_wizard(monkeypatch, choice_seq, text_map):
    """Helper: run wizard with scripted answers, return WomanConfig.

    choice_seq: list of answers for prompt_choice calls in order
    (ui_mode, ai_provider, auto_update, index_mode, man_page_limit)

    text_map: dict of {substring → answer} for prompt_text calls
    """
    import woman_revamp.wizard as _wiz

    choice_iter = iter(choice_seq)

    def fake_choice(label, choices, default=None):
        return next(choice_iter)

    def fake_text(label, default=""):
        for key, val in text_map.items():
            if key.lower() in label.lower():
                return val
        return default

    monkeypatch.setattr(_wiz, "prompt_choice", fake_choice)
    monkeypatch.setattr(_wiz, "prompt_text", fake_text)
    monkeypatch.setattr(_wiz, "show_banner", lambda: None)
    monkeypatch.setattr(WomanConfig, "save", lambda self: None)
    monkeypatch.setattr(_wiz, "refresh_all", lambda **kw: None)

    return _wiz.run_setup()


class TestWizardOpenAIEndpoint:
    """openai provider must prompt for custom endpoint URL."""

    def test_wizard_openai_stores_custom_endpoint(self, monkeypatch):
        cfg = _run_wizard(
            monkeypatch,
            choice_seq=["rich", "openai", "yes", "jit", "300"],
            text_map={
                "api key": "",
                "custom base url": "https://ngrok.example.com/v1/chat/completions",
                "model name": "gpt-4o-mini",
            },
        )
        assert cfg.ai_endpoint == "https://ngrok.example.com/v1/chat/completions"

    def test_wizard_openai_stores_model_name(self, monkeypatch):
        cfg = _run_wizard(
            monkeypatch,
            choice_seq=["rich", "openai", "yes", "jit", "300"],
            text_map={
                "api key": "",
                "custom base url": "",
                "model name": "qwen3:30b",
            },
        )
        assert cfg.ai_backend == "qwen3:30b"

    def test_wizard_openai_blank_endpoint_keeps_empty(self, monkeypatch):
        """Blank endpoint means use OpenAI's default URL (config stores empty string)."""
        cfg = _run_wizard(
            monkeypatch,
            choice_seq=["rich", "openai", "yes", "jit", "300"],
            text_map={"api key": "sk-test", "custom base url": "", "model name": "gpt-4o-mini"},
        )
        assert cfg.ai_endpoint == ""
        assert cfg.ai_api_key == "sk-test"


class TestWizardOllamaModelName:
    """ollama provider must prompt for model name (not hardcode 'ollama')."""

    def test_wizard_ollama_stores_model_name(self, monkeypatch):
        cfg = _run_wizard(
            monkeypatch,
            choice_seq=["rich", "ollama", "yes", "jit", "300"],
            text_map={
                "ollama endpoint": "http://localhost:11434",
                "model name": "qwen3:30b",
            },
        )
        assert cfg.ai_backend == "qwen3:30b"

    def test_wizard_ollama_model_not_hardcoded_ollama(self, monkeypatch):
        """ai_backend must NOT be the literal string 'ollama' when user enters a model."""
        cfg = _run_wizard(
            monkeypatch,
            choice_seq=["rich", "ollama", "yes", "jit", "300"],
            text_map={
                "ollama endpoint": "http://localhost:11434",
                "model name": "mistral",
            },
        )
        assert cfg.ai_backend != "ollama"
        assert cfg.ai_backend == "mistral"
