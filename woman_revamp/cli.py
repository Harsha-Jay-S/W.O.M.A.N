"""CLI entry point for the woman_revamp package."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from .config import CONFIG_FILE, WomanConfig, ensure_directories
from .context import get_active_files, get_shell_history
from .engine import MIN_CONFIDENCE, call_local_registry, extract_intent, extract_numbers, rank_candidates
from .explain import explain_command
from .manual import show_man_page
from .shell_integration import generate_shell_integration
from .ml import WomanReranker, decide_action

_reranker: WomanReranker | None = None

def _get_reranker() -> WomanReranker:
    global _reranker
    if _reranker is None:
        _reranker = WomanReranker()
    return _reranker
from .errors import render_user_error
from .indexer.cache import registry_needs_refresh, refresh_registry_cache
from .indexer.controller import index_one
from .indexer.providers import AIProviderSpec
from .registry import get_registry, normalize_os_name
from .ui import (
    Choice,
    Console,
    auto_detect_lean_mode,
    confidence_label,
    danger_badge,
    get_console,
    prompt_choice,
    prompt_command_action,
    prompt_text,
    show_banner,
    show_progress,
    spinner,
    syntax_block,
)
from .wizard import run_setup


EXAMPLE_QUERIES = [
    'woman "list all files including hidden"',
    'woman "find files modified in the last 7 days"',
    'woman "show running processes"',
    'woman "search for text in files"',
    'woman "check disk usage"',
    'woman "install a python package"',
    'woman "show git log"',
    'woman "kill a process by name"',
]


def _show_no_match(
    query: str,
    candidates: list[dict[str, object]],
    context: object,
    os_name: str,
) -> None:
    """Print did-you-mean suggestions or example queries when no match found."""
    from .engine import MIN_CONFIDENCE
    console = get_console()
    console.print(f'\n[bold #e1306c]No confident match[/bold #e1306c] for [italic]"{query}"[/italic]\n')

    # Near-miss: show closest matches if any scored > 0
    near = [c for c in candidates if float(c.get("score", 0.0)) > 0.0]
    if near:
        console.print("[dim]Closest matches:[/dim]")
        for item in near[:3]:
            score = float(item.get("score", 0.0))
            kw_sample = ""
            rendered = str(item.get("rendered") or item.get("command") or "")
            console.print(f'  [dim]woman "{rendered}"[/dim]  [{score:.2f}]')
        console.print()

    # Complete miss: show example queries
    if not near:
        console.print("[dim]Try one of these example queries:[/dim]")
        import random
        for example in random.sample(EXAMPLE_QUERIES, min(3, len(EXAMPLE_QUERIES))):
            console.print(f"  [dim]{example}[/dim]")
        console.print()

    # Suggest AI config if not configured
    try:
        from .config import WomanConfig
        cfg = WomanConfig.load()
        if cfg.ai_provider == "none":
            console.print("[dim]Or set up an AI provider for broader coverage:[/dim]  [bold]woman config[/bold]")
    except Exception:
        pass


def _ask_ai_directly(
    query: str, context: str, os_name: str, config: "WomanConfig"
) -> str:
    """Ask the configured AI provider to generate a shell command directly."""
    from .indexer.providers import AIProviderSpec, fetch_provider_text

    spec = AIProviderSpec(
        provider=config.ai_provider,
        endpoint=getattr(config, "ai_endpoint", ""),
        api_key=getattr(config, "ai_api_key", ""),
        model=getattr(config, "ai_backend", ""),
    )
    prompt = (
        f"Return ONLY a single shell command with no explanation.\n"
        f"OS: {os_name}\n"
        f"Context:\n{context[:500]}\n"
        f"Query: {query}"
    )
    raw = fetch_provider_text(spec, prompt)
    if not raw:
        return ""
    raw = raw.strip()
    # Basic validation: must be a plausible shell command
    if raw.lower().startswith(("i ", "sorry", "unfortunately", "as an ai")):
        return ""
    if "\n" in raw and raw.count("\n") > 2:
        return ""
    return raw


def _copy_to_clipboard(command: str) -> bool:
    """Copy command to OS clipboard. Returns True on success."""
    try:
        if sys.platform == "darwin" and shutil.which("pbcopy"):
            proc = subprocess.run(["pbcopy"], input=command.encode(), check=True)
            return proc.returncode == 0
        if sys.platform.startswith("linux"):
            if shutil.which("wl-copy"):
                proc = subprocess.run(["wl-copy"], input=command.encode(), check=True)
                return proc.returncode == 0
            if shutil.which("xclip"):
                proc = subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=command.encode(), check=True,
                )
                return proc.returncode == 0
            if shutil.which("xsel"):
                proc = subprocess.run(
                    ["xsel", "--clipboard", "--input"],
                    input=command.encode(), check=True,
                )
                return proc.returncode == 0
        if sys.platform == "win32" and shutil.which("clip"):
            proc = subprocess.run(["clip"], input=command.encode(), check=True)
            return proc.returncode == 0
    except (subprocess.CalledProcessError, OSError):
        pass
    return False


def _command_comment(intents: list[str], signals: dict[str, object], rendered: str) -> str:
    """Generate a one-liner human comment about what the command does."""
    words = rendered.split()
    cmd_name = words[0] if words else ""
    sub_cmd = words[1] if len(words) > 1 and not words[1].startswith("-") else ""

    intent_verb_map = {
        "search":   "searches for files",
        "find":     "finds files",
        "delete":   "deletes files",
        "remove":   "removes files",
        "copy":     "copies files",
        "move":     "moves files",
        "list":     "lists files",
        "show":     "shows info",
        "run":      f"runs {cmd_name}",
        "execute":  f"runs {cmd_name}",
        "install":  "installs package",
        "update":   "updates",
        "kill":     "kills process",
        "check":    f"shows {cmd_name} status",
        "compress": "creates archive",
        "extract":  "extracts archive",
        "count":    "counts lines",
        "monitor":  "monitors live",
        "git":      f"git {sub_cmd}".strip() if sub_cmd else "runs git",
        "status":   f"shows {cmd_name} status",
        "network":  "shows network info",
        "disk":     "shows disk usage",
        "process":  "shows processes",
    }
    cmd_fallback_map = {
        "git":        f"git {sub_cmd}".strip() if sub_cmd else "runs git",
        "ls":         "lists files in directory",
        "find":       "finds files",
        "grep":       "searches file contents",
        "ps":         "shows running processes",
        "df":         "shows disk free space",
        "du":         "shows directory sizes",
        "kill":       "kills process",
        "pkill":      "kills matching process",
        "tar":        "archives files",
        "zip":        "creates zip archive",
        "cp":         "copies files",
        "mv":         "moves/renames files",
        "rm":         "removes files",
        "chmod":      "changes file permissions",
        "ssh":        "connects via SSH",
        "curl":       "fetches URL",
        "wget":       "downloads file",
        "systemctl":  f"manages {sub_cmd} service" if sub_cmd else "manages service",
        "apt":        f"apt {sub_cmd}".strip() if sub_cmd else "manages packages",
        "pip":        f"pip {sub_cmd}".strip() if sub_cmd else "manages Python packages",
        "docker":     f"docker {sub_cmd}".strip() if sub_cmd else "manages containers",
        "lsof":       "lists open files/ports",
        "ss":         "shows socket/port info",
        "netstat":    "shows network connections",
        "htop":       "monitors processes",
        "top":        "monitors processes",
    }

    if intents:
        base = intent_verb_map.get(intents[0], cmd_fallback_map.get(cmd_name, f"runs {cmd_name}"))
    else:
        base = cmd_fallback_map.get(cmd_name, f"runs {cmd_name}")

    # Append contextual detail from signals
    if "port" in signals:
        base = base.replace("process", f"process on port {signals['port']}")
        if "process" not in base and "port" not in base:
            base += f" on port {signals['port']}"
    elif "pid" in signals:
        base += f" (PID {signals['pid']})"
    elif "days" in signals and any(w in base for w in ("find", "search", "file")):
        base += f" modified in the last {signals['days']} day(s)"
    elif "lines" in signals and "lines" not in base:
        base += f" (first {signals['lines']} lines)"

    return "# " + base


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
    parser.add_argument(
        "--config",
        action="store_true",
        help="Run the setup wizard",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the command and exit without executing",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Show a structured breakdown of the command",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Open the man page for the identified command",
    )
    return parser


def build_subcommand_parser() -> argparse.ArgumentParser:
    """Build a parser with subcommands for woman."""
    parser = argparse.ArgumentParser(prog="woman")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    sp = subparsers.add_parser("search", aliases=["s"], help="Translate natural language to a command")
    sp.add_argument("query", nargs="+")
    sp.add_argument("--os", dest="os_name")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--top", type=int, default=5)

    sp = subparsers.add_parser("list", help="List indexed commands")
    sp.add_argument("--os", dest="os_name")

    sp = subparsers.add_parser("explain", help="Explain a generated command")
    sp.add_argument("query", nargs="+")

    sp = subparsers.add_parser("manual", aliases=["man"], help="Show the man page for a command")
    sp.add_argument("command", nargs="+")

    subparsers.add_parser("config", help="Run the setup wizard")

    sp = subparsers.add_parser("index", help="Manage the command index")
    index_sub = sp.add_subparsers(dest="index_action")
    index_sub.add_parser("refresh", help="Re-scan all PATH tools")
    index_sub.add_parser("list", help="List indexed tools")
    add_p = index_sub.add_parser("add", help="Index a specific tool")
    add_p.add_argument("tool")

    sp = subparsers.add_parser("shell-integration", help="Generate shell integration code")
    sp.add_argument("shell", nargs="?", choices=["bash", "zsh", "fish"], default="bash")

    sp = subparsers.add_parser("history", help="Show recent query history")
    sp.add_argument("--count", type=int, default=20, help="Number of entries to show")

    subparsers.add_parser("redo", help="Re-run the last executed command")

    sp = subparsers.add_parser("why", help="Show scoring breakdown for a query")
    sp.add_argument("query", nargs="+")
    sp.add_argument("--os", dest="os_name")

    return parser


_SUBCOMMANDS = {
    "search", "s", "list", "explain", "manual", "man", "config", "index",
    "shell-integration", "history", "redo", "why",
}


def _handle_subcommand(args: argparse.Namespace) -> int:
    """Handle a subcommand dispatch. Returns exit code."""
    sc = args.subcommand

    if sc == "config":
        if not auto_detect_lean_mode():
            try: show_banner()
            except: pass
        run_setup()
        return 0

    if sc == "list":
        os_name = normalize_os_name(getattr(args, "os_name", None))
        for name in sorted(get_registry(os_name)):
            print(name)
        return 0

    if sc in ("manual", "man"):
        cmd = " ".join(args.command).strip()
        if not cmd:
            print("woman manual: a command name is required", file=sys.stderr)
            return 2
        return show_man_page(cmd.split()[0])

    if sc == "shell-integration":
        shell = getattr(args, "shell", "bash") or "bash"
        print(generate_shell_integration(shell))
        return 0

    if sc == "history":
        from .query_history import load_history
        import time as _time
        entries = load_history(n=getattr(args, "count", 20))
        if not entries:
            print("No history yet.")
            return 0
        console = get_console()
        for entry in entries:
            ts = _time.strftime("%Y-%m-%d %H:%M", _time.localtime(entry.timestamp))
            console.print(f"[dim]{ts}[/dim]  [{entry.action}]  {entry.rendered}  [dim]({entry.query})[/dim]")
        return 0

    if sc == "redo":
        from .query_history import last_executed
        entry = last_executed()
        if not entry:
            print("No executed commands in history.", file=sys.stderr)
            return 1
        console = get_console()
        from .ml.safety import calculate_danger_score as _redo_danger
        _redo_dscore, _redo_dreasons = _redo_danger(entry.rendered)
        console.print()
        console.print(syntax_block(entry.rendered))
        if _redo_dscore >= 0.4 and _redo_dreasons:
            console.print(danger_badge(_redo_dscore, _redo_dreasons))
        action_key = prompt_command_action(entry.rendered, _redo_dscore, _redo_dreasons)
        if action_key in ("cancel", "abort"):
            print("Cancelled.")
            return 0
        if action_key == "copy":
            _copy_to_clipboard(entry.rendered)
            return 0
        if action_key == "edit":
            entry_cmd = prompt_text("Edit command", default=entry.rendered)
        else:
            entry_cmd = entry.rendered
        try:
            print()
            return subprocess.run(entry_cmd, shell=True, check=False).returncode
        except OSError as exc:
            print(render_user_error(exc), file=sys.stderr)
            return 1

    if sc == "why":
        query_parts = getattr(args, "query", [])
        q = " ".join(query_parts)
        os_n = normalize_os_name(getattr(args, "os_name", None))
        results = rank_candidates(q, os_info=os_n, limit=3)
        if not results:
            print("No results.", file=sys.stderr)
            return 1
        console = get_console()
        for item in results:
            score = float(item.get("score", 0.0))
            rendered = str(item.get("rendered") or item.get("command") or "")
            source = str(item.get("source", "heuristic"))
            intent = str(item.get("intent") or "")
            template = str(item.get("template") or "")
            from .ui import confidence_label_plain
            conf = confidence_label_plain(score)
            console.print(f"\n[bold]{item['command']}[/bold]  {conf}  (score {score:.3f})")
            console.print(f"  Rendered:  {rendered}")
            console.print(f"  Template:  {template}")
            console.print(f"  Intent:    {intent}")
            console.print(f"  Source:    {source}")
        return 0

    if sc == "index":
        config = WomanConfig.load()
        provider = AIProviderSpec(
            provider=config.ai_provider, endpoint=config.ai_endpoint,
            api_key=config.ai_api_key, model=config.ai_backend,
        )
        action = getattr(args, "index_action", None)
        if action == "refresh" or action is None:
            show_progress("Refreshing registry cache...")
            refresh_registry_cache(provider=provider, ai_mode=False, man_page_limit=300)
            print("registry refreshed")
            return 0
        if action == "add":
            show_progress(f"Indexing {args.tool}...")
            use_ai = provider is not None and provider.provider not in ("none", "")
            index_one(args.tool, provider=provider, ai_mode=use_ai, man_page_limit=300)
            print(f"indexed {args.tool}")
            return 0
        if action == "list":
            for name in sorted(get_registry(normalize_os_name(None))):
                print(name)
            return 0
        print("woman index: available actions: refresh, list, add <tool>", file=sys.stderr)
        return 2

    return None


def main(argv: Sequence[str] | None = None) -> int:
    ensure_directories()

    # Subcommand mode detection
    if argv is None:
        argv = (sys.argv[1:] if hasattr(sys, "argv") else [])
    # No args → show subcommand help and exit cleanly
    if not argv:
        build_subcommand_parser().print_help()
        return 0
    # --help / -h → delegate to subcommand parser so user sees subcommand interface
    if argv[0] in ("--help", "-h"):
        build_subcommand_parser().parse_args(["--help"])  # raises SystemExit(0)
    if argv and argv[0] in _SUBCOMMANDS:
        sub_parser = build_subcommand_parser()
        sub_args = sub_parser.parse_args(argv)
        code = _handle_subcommand(sub_args)
        if code is not None:
            return code
        # search/explain — rebuild legacy argv and fall through
        sc = sub_args.subcommand
        legacy_argv: list[str] = []
        os_name = getattr(sub_args, "os_name", None)
        if os_name:
            legacy_argv.extend(["--os", os_name])
        if sc in ("search", "s"):
            if getattr(sub_args, "json", False):
                legacy_argv.append("--json")
            if getattr(sub_args, "dry_run", False):
                legacy_argv.append("--dry-run")
            top = getattr(sub_args, "top", 5)
            if top != 5:
                legacy_argv.extend(["--top", str(top)])
        elif sc == "explain":
            legacy_argv.append("--explain")
        legacy_argv.extend(sub_args.query)
        argv = legacy_argv

    parser = build_parser()
    args = parser.parse_args(argv)

    # Only show banner on interactive TTY
    if not auto_detect_lean_mode():
        try:
            show_banner()
        except Exception:
            pass

    is_query = bool(args.query)

    # Zero-config: lazy wizard — only prompt when a real query is given
    if not CONFIG_FILE.exists():
        if is_query:
            run_setup()
    elif registry_needs_refresh():
        config = WomanConfig.load()
        if config.auto_update_registry:
            decision = prompt_choice(
                "New PATH tools detected. Refresh woman fallback cache?",
                [
                    Choice(
                        "refresh", "Refresh now", "scan new tools and man/help text"
                    ),
                    Choice("skip", "Skip this time", "keep current cache"),
                    Choice(
                        "disable",
                        "Disable prompts",
                        "stop asking on future PATH changes",
                    ),
                ],
                default="refresh",
            )
            if decision == "refresh":
                provider = AIProviderSpec(
                    provider=config.ai_provider,
                    endpoint=config.ai_endpoint,
                    api_key=config.ai_api_key,
                    model=config.ai_backend,
                )
                show_progress("Refreshing registry cache...")
                refresh_registry_cache(
                    provider=provider,
                    ai_mode=config.ai_provider != "none"
                    and config.index_mode == "batch",
                    man_page_limit=config.man_page_limit,
                )
            elif decision == "disable":
                config.auto_update_registry = False
                config.save()

    if args.config:
        run_setup()
        return 0

    if args.refresh_index:
        config = WomanConfig.load()
        provider = AIProviderSpec(
            provider=config.ai_provider,
            endpoint=config.ai_endpoint,
            api_key=config.ai_api_key,
            model=config.ai_backend,
        )
        show_progress("Refreshing registry cache...")
        refresh_registry_cache(
            provider=provider,
            ai_mode=config.ai_provider != "none" and config.index_mode == "batch",
            man_page_limit=config.man_page_limit,
        )
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
        index_one(
            args.index_tool,
            provider=provider,
            ai_mode=config.ai_provider != "none" and config.index_mode == "batch",
            man_page_limit=config.man_page_limit,
        )
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
        if args.manual:
            parser.error("a command name is required with --manual")
        parser.error("a query is required unless --list is used")

    if args.manual:
        command_name = query.split()[0]
        return show_man_page(command_name)

    context = args.context.strip()
    active_files = None
    project_signals = None
    if not context:
        from .context import get_project_signals
        cwd = Path.cwd()
        active_files = get_active_files(cwd, max_files=200)
        project_signals = get_project_signals(cwd, active_files=active_files)
        context = "\n".join(
            [f"Current directory: {cwd}", "Files:"] + [p.name for p in active_files]
        )
    history = get_shell_history(5)
    if history:
        context = "\n\n".join([context, "Recent shell history:\n" + "\n".join(history)])

    if args.json:
        payload = rank_candidates(
            query,
            context=context,
            os_info=os_name,
            limit=args.top,
            active_files=active_files,
            project_signals=project_signals,
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.explain:
        explanation = explain_command(query, context=context, os_info=os_name)
        print(explanation)
        return 0

    candidates = rank_candidates(
        query,
        context=context,
        os_info=os_name,
        limit=max(5, args.top),
        active_files=active_files,
        project_signals=project_signals,
    )
    reranker = _get_reranker()
    history = get_shell_history(5)
    decision: dict[str, object] = {"action": "confirm"}
    if reranker.available:
        ranked = reranker.rerank(query, os_name, history, candidates)
        decision = decide_action(ranked, already_ranked=True)
        if decision.get("action") == "show_choices":
            console = get_console()
            console.print()
            for item in ranked[: min(len(ranked), args.top)]:
                console.print(
                    syntax_block(
                        f"[{item.get('ml_score', 0.0):.2f}] "
                        f"{item.get('rendered') or item.get('command') or item.get('candidate_command', '')}"
                    )
                )
            print("no confident local match")
            return 1

        if decision.get("action") == "no_match":
            command = call_local_registry(query, context=context, os_info=os_name)
        else:
            raw = decision.get("command") or ""
            command = str(raw).strip() if raw and str(raw) != "None" else ""
            if not command and ranked:
                command = str(
                    ranked[0].get("rendered")
                    or ranked[0].get("command")
                    or ranked[0].get("candidate_command")
                    or ""
                )
    else:
        # Use candidates already computed with project_signals; fall back only when empty
        best = candidates[0] if candidates else None
        if best and float(best.get("score", 0.0)) >= MIN_CONFIDENCE:
            command = str(best.get("rendered") or best.get("command") or "").strip()
            decision = {**decision, "score": best.get("score")}
        else:
            command = ""

    # Always run danger scoring regardless of ML model availability
    if command and not decision.get("danger_score"):
        from .ml.safety import calculate_danger_score as _calc_danger
        d_score, d_reasons = _calc_danger(command)
        decision = {**decision, "danger_score": d_score, "danger_reasons": d_reasons}

    if command:
        # Extract signals + intents for inline comment
        intents_for_comment = list(extract_intent(query))
        signals_for_comment = dict(extract_numbers(query))
        inline_comment = _command_comment(intents_for_comment, signals_for_comment, command)

        conf_score = float(
            decision.get("score")
            or (candidates[0].get("score") if candidates else 0.0)
            or 0.0
        )

        get_console().print()
        get_console().print(syntax_block(command))
        get_console().print(f"[dim]{inline_comment}[/dim]")
        get_console().print(confidence_label(conf_score))

        # Safety badge for destructive commands
        danger_score = float(decision.get("danger_score", 0.0))
        danger_reasons = list(decision.get("danger_reasons", []))
        if danger_score >= 0.4 and danger_reasons:
            Console().print(danger_badge(danger_score, danger_reasons))

        # Dry run — show command and exit
        if args.dry_run:
            print("[Dry run] Command not executed.")
            return 0

        # Multi-action prompt loop
        if str(decision.get("action", "confirm")) == "auto_accept" and danger_score < 0.85:
            action_key = "execute"
        else:
            action_key = prompt_command_action(command, danger_score, danger_reasons)

        while action_key != "execute":
            if action_key in ("cancel", "abort"):
                print("Cancelled.")
                return 0
            if action_key == "copy":
                success = _copy_to_clipboard(command)
                if success:
                    Console().print("[dim]  ✓ Copied to clipboard[/dim]")
                else:
                    Console().print(f"[dim]  Could not access clipboard. Command:[/dim]\n  {command}")
                # After copy, offer execute or cancel
                action_key = prompt_choice(
                    "Also execute now?",
                    [
                        Choice("execute", "▶ Execute", "run the command now"),
                        Choice("cancel",  "✕ Cancel",  "done"),
                    ],
                    default="cancel",
                )
                continue
            if action_key == "review":
                Console().print(syntax_block(command))
                if danger_reasons:
                    Console().print(danger_badge(danger_score, danger_reasons))
                action_key = prompt_command_action(command, danger_score, danger_reasons)
            elif action_key == "edit":
                command = prompt_text("Edit command", default=command)
                Console().print()
                Console().print(syntax_block(command))
                # Re-score danger after edit
                from .ml.safety import calculate_danger_score as _calc_danger
                danger_score, danger_reasons = _calc_danger(command)
                action_key = prompt_command_action(command, danger_score, danger_reasons)
            else:
                action_key = prompt_command_action(command, danger_score, danger_reasons)

        print()
        try:
            completed = subprocess.run(command, shell=True, check=False)
        except PermissionError as exc:
            print(render_user_error(exc), file=sys.stderr)
            return 1
        except FileNotFoundError as exc:
            print(render_user_error(exc), file=sys.stderr)
            return 1
        except OSError as exc:
            print(render_user_error(exc), file=sys.stderr)
            return 1
        # Record to history
        try:
            from .query_history import HistoryEntry, append_history
            import time as _time
            append_history(HistoryEntry(
                timestamp=_time.time(),
                query=query,
                rendered=command,
                action="execute",
                os=os_name,
            ))
        except Exception:
            pass
        return completed.returncode

    # Direct AI fallback when no local match is found
    if config.ai_provider not in ("none", ""):
        with spinner("Asking AI..."):
            ai_command = _ask_ai_directly(query, context, os_name, config)
        if ai_command:
            from .ml.safety import calculate_danger_score as _calc_danger2
            ai_danger, ai_reasons = _calc_danger2(ai_command)
            decision = {"danger_score": ai_danger, "danger_reasons": ai_reasons, "score": 0.5}
            candidates = [{"command": ai_command, "score": 0.5, "rendered": ai_command,
                           "template": "ai_direct", "intent": None, "source": "ai"}]
            command = ai_command
            # Re-enter the command display + action loop
            intents_for_comment = list(extract_intent(query))
            signals_for_comment = dict(extract_numbers(query))
            inline_comment = _command_comment(intents_for_comment, signals_for_comment, command)
            get_console().print()
            get_console().print(syntax_block(command))
            get_console().print(f"[dim]{inline_comment}[/dim]")
            get_console().print(f"[dim](source: AI — {config.ai_provider})[/dim]")
            if ai_danger >= 0.4 and ai_reasons:
                Console().print(danger_badge(ai_danger, ai_reasons))
            if not args.dry_run:
                action_key = prompt_command_action(command, ai_danger, ai_reasons)
                if action_key in ("cancel", "abort"):
                    print("Cancelled.")
                    return 0
                if action_key == "copy":
                    _copy_to_clipboard(command)
                    return 0
                if action_key == "edit":
                    command = prompt_text("Edit command", default=command)
                try:
                    print()
                    return subprocess.run(command, shell=True, check=False).returncode
                except OSError as exc:
                    print(render_user_error(exc), file=sys.stderr)
                    return 1
            return 0

    _show_no_match(query, candidates, context, os_name)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
