"""First-run configuration wizard for woman_revamp."""

from __future__ import annotations

from .config import WomanConfig
from .indexer.controller import refresh_all
from .indexer.providers import AIProviderSpec
from .ui import Choice, prompt_choice, prompt_text, show_banner


def run_setup() -> WomanConfig:
    show_banner()
    print("Configure woman once, then it will keep the registry fresh.")
    ui_mode = prompt_choice(
        "Choose setup UI style:",
        [Choice("rich", "Rich UI", "purple terminal panels if available"), Choice("basic", "Basic UI", "stdlib fallback")],
        default="rich",
    )
    ai_provider = prompt_choice(
        "Choose AI fallback mode:",
        [
            Choice("none", "Heuristics only", "no AI fallback"),
            Choice("ollama", "Ollama", "local LLM"),
            Choice("openai", "OpenAI", "API key"),
            Choice("anthropic", "Anthropic", "API key"),
            Choice("gemini", "Google Gemini", "API key"),
        ],
        default="none",
    )
    backend = ""
    endpoint = ""
    api_key = ""
    if ai_provider == "ollama":
        backend = "ollama"
        endpoint = prompt_text("Ollama endpoint", "http://localhost:11434")
    elif ai_provider in {"openai", "anthropic", "gemini"}:
        backend = ai_provider
        api_key = prompt_text(f"{ai_provider.title()} API key", "")
    auto_update = prompt_choice(
        "Automatically refresh registry when PATH changes?",
        [Choice("yes", "Yes"), Choice("no", "No")],
        default="yes",
    ) == "yes"
    index_mode = prompt_choice(
        "Choose indexing mode:",
        [Choice("jit", "Just-in-time", "index tools when needed"), Choice("batch", "Batch", "scan PATH now")],
        default="jit",
    )
    man_page_limit = int(
        prompt_choice(
            "Choose man-page extraction depth:",
            [Choice("300", "First 300 lines", "default fast path"), Choice("0", "Entire man page", "for benchmarking")],
            default="300",
        )
    )
    config = WomanConfig(
        ui_mode=ui_mode,
        ai_provider=ai_provider,
        ai_backend=backend,
        ai_endpoint=endpoint,
        ai_api_key=api_key,
        auto_update_registry=auto_update,
        index_mode=index_mode,
        man_page_limit=man_page_limit,
    )
    config.save()
    provider = AIProviderSpec(provider=ai_provider, endpoint=endpoint, api_key=api_key, model=backend)
    refresh_all(provider=provider, ai_mode=(ai_provider != "none" and index_mode == "batch"), man_page_limit=config.man_page_limit)
    return config
