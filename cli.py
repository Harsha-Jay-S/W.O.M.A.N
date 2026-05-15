"""CLI entry point for the woman_revamp package."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from .config import CONFIG_FILE, WomanConfig, ensure_directories
from .context import get_shell_history
from .engine import call_local_registry, rank_candidates
from .indexer.cache import registry_needs_refresh, refresh_registry_cache
from .indexer.controller import index_one
from .indexer.providers import AIProviderSpec
from .registry import get_registry, normalize_os_name
from .ui import Choice, prompt_choice, show_progress, syntax_block
from .wizard import run_setup


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="woman-revamp",
        description="Local registry and scoring engine for woman commands.",
    )
    parser.add_argument("query", nargs="*", help="Natural language query")
    parser.add_argument(
        "--os",
        dest="os_name",
        help="Override detected OS (linux, macos, windows)",
    )
    parser.add_argument(
        "--context",
        default="",
        help="Optional context text such as cwd listing or history",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON with the top ranked matches",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="How many ranked matches to show with --json",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List registry commands for the selected OS",
    )
    parser.add_argument(
        "--refresh-index",
        action="store_true",
        help="Refresh the cached registry",
    )
    parser.add_argument(
        "--index-tool",
        default="",
        help="Index one tool and refresh cache",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    ensure_directories()
    if not CONFIG_FILE.exists():
        run_setup()
    elif registry_needs_refresh():
        config = WomanConfig.load()
        if config.auto_update_registry:
            decision = prompt_choice(
                "New PATH tools detected. Refresh woman fallback cache?",
                [
                    Choice("refresh", "Refresh now", "scan new tools and man/help text"),
                    Choice("skip", "Skip this time", "keep current cache"),
                    Choice("disable", "Disable prompts", "stop asking on future PATH changes"),
                ],
                default="1",
            )
            if decision == "refresh":
                provider = AIProviderSpec(
                    provider=config.ai_provider,
                    endpoint=config.ai_endpoint,
                    api_key=config.ai_api_key,
                    model=config.ai_backend,
                )
                show_progress("Refreshing registry cache...")
                refresh_registry_cache(provider=provider, ai_mode=config.ai_provider != "none" and config.index_mode == "batch", man_page_limit=config.man_page_limit)
            elif decision == "disable":
                config.auto_update_registry = False
                config.save()

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.refresh_index:
        config = WomanConfig.load()
        provider = AIProviderSpec(
            provider=config.ai_provider,
            endpoint=config.ai_endpoint,
            api_key=config.ai_api_key,
            model=config.ai_backend,
        )
        show_progress("Refreshing registry cache...")
        refresh_registry_cache(provider=provider, ai_mode=config.ai_provider != "none" and config.index_mode == "batch", man_page_limit=config.man_page_limit)
        print("registry refreshed")
        return 0

    if args.index_tool:
        config = WomanConfig.load()
        provider = AIProviderSpec(
            provider=config.ai_provider,
            endpoint=config.ai_endpoint,
            api_key=config.ai_api_key,
            model=config.ai_backend,
        )
        show_progress(f"Indexing {args.index_tool}...")
        index_one(args.index_tool, provider=provider, ai_mode=config.ai_provider != "none" and config.index_mode == "batch", man_page_limit=config.man_page_limit)
        print(f"indexed {args.index_tool}")
        return 0

    os_name = normalize_os_name(args.os_name)
    query = " ".join(args.query).strip()

    if args.list:
        registry = get_registry(os_name)
        for name in sorted(registry):
            print(name)
        return 0

    if not query:
        parser.error("a query is required unless --list is used")

    context = args.context.strip()
    if not context:
        cwd = Path.cwd()
        entries = sorted(p.name for p in cwd.iterdir())
        context = "\n".join([f"Current directory: {cwd}", "Files:"] + entries[:200])
    history = get_shell_history(5)
    if history:
        context = "\n\n".join([context, "Recent shell history:\n" + "\n".join(history)])

    if args.json:
        payload = rank_candidates(query, context=context, os_info=os_name, limit=args.top)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    command = call_local_registry(query, context=context, os_info=os_name)
    if command:
        from rich.console import Console

        Console().print()
        Console().print(syntax_block(command))
        try:
            import questionary

            answer = questionary.confirm("Execute this command?").ask()
        except (KeyboardInterrupt, EOFError):
            print(f"\nAborted.")
            return 0

        if answer:
            print()
            completed = subprocess.run(command, shell=True)
            return completed.returncode
        print("Aborted.")
        return 0

    print("no confident local match", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
