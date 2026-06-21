"""Terminal UI helpers for woman_revamp."""

from __future__ import annotations

import shutil
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable

try:
    from rich.console import Console as _Console
    from rich.syntax import Syntax as _Syntax
    from rich.text import Text as _Text
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False

PURPLE_STOPS = ["#5851db", "#833ab4", "#c13584", "#e1306c", "#fd1d1d"]

BANNER_ART = r"""
██╗    ██╗ ██████╗ ███╗   ███╗ █████╗ ███╗   ██╗
██║    ██║██╔═══██╗████╗ ████║██╔══██╗████╗  ██║
██║ █╗ ██║██║   ██║██╔████╔██║███████║██╔██╗ ██║
██║███╗██║██║   ██║██║╚██╔╝██║██╔══██║██║╚██╗██║
╚███╔███╔╝╚██████╔╝██║ ╚═╝ ██║██║  ██║██║ ╚████║
 ╚══╝╚══╝  ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝
""".strip("\n").splitlines()


class _PlainConsole:
    """Minimal Console substitute used when Rich is not installed."""

    def print(self, *args: object, **_kwargs: object) -> None:
        import re
        text = " ".join(str(a) for a in args)
        print(re.sub(r"\[/?[^\]]+\]", "", text))


def get_console() -> object:
    """Return a Rich Console, or a plain fallback if Rich is unavailable."""
    return _Console() if _RICH_AVAILABLE else _PlainConsole()


def Console() -> object:  # noqa: N802 — intentional alias for Rich's Console
    return get_console()


@dataclass(frozen=True)
class Choice:
    key: str
    label: str
    description: str = ""


def has_rich() -> bool:
    return _RICH_AVAILABLE


def _terminal_width() -> int:
    return shutil.get_terminal_size(fallback=(80, 24)).columns


def _lerp_hex(a: str, b: str, t: float) -> str:
    ar, ag, ab = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
    br, bg, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    bl = round(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{bl:02x}"


def _column_color(col: int, width: int) -> str:
    if width <= 1:
        return PURPLE_STOPS[0]
    t = col / (width - 1)
    seg = t * (len(PURPLE_STOPS) - 1)
    i = min(int(seg), len(PURPLE_STOPS) - 2)
    return _lerp_hex(PURPLE_STOPS[i], PURPLE_STOPS[i + 1], seg - i)


def gradient_text(lines: Iterable[str]) -> str:
    """Render lines with a horizontal per-column Instagram-purple gradient.

    Color is keyed on the global column index so the same column shares one hue
    across all rows. Spaces are emitted raw (no glyph); the returned string is
    Rich markup, which ``_PlainConsole`` strips back to raw art when Rich is
    absent.
    """
    lines = list(lines)
    width = max((len(line) for line in lines), default=0)
    out: list[str] = []
    for line in lines:
        parts: list[str] = []
        run_chars: list[str] = []
        run_color: str | None = None
        for col, ch in enumerate(line):
            if ch == " ":
                if run_chars:
                    parts.append(f"[{run_color}]{''.join(run_chars)}[/]")
                    run_chars = []
                    run_color = None
                parts.append(" ")
                continue
            color = _column_color(col, width)
            if color != run_color and run_chars:
                parts.append(f"[{run_color}]{''.join(run_chars)}[/]")
                run_chars = []
            run_color = color
            run_chars.append(ch)
        if run_chars:
            parts.append(f"[{run_color}]{''.join(run_chars)}[/]")
        out.append("".join(parts))
    return "\n".join(out)


def show_banner() -> None:
    get_console().print(gradient_text(BANNER_ART), highlight=False)


def show_progress(message: str) -> None:
    get_console().print(f"[bold #c13584]{message}[/bold #c13584]")


def confidence_label(score: float) -> str:
    """Return a styled confidence label for a command score."""
    if score >= 0.80:
        return "[bold green]● High[/bold green]"
    if score >= 0.55:
        return "[bold yellow]● Moderate[/bold yellow]"
    if score >= 0.30:
        return "[bold #ff8c00]● Low[/bold #ff8c00]"
    return "[dim]● Very low[/dim]"


def confidence_label_plain(score: float) -> str:
    """Return a plain (no markup) confidence label."""
    if score >= 0.80:
        return "● High"
    if score >= 0.55:
        return "● Moderate"
    if score >= 0.30:
        return "● Low"
    return "● Very low"


@contextmanager
def spinner(message: str):
    """Context manager that shows a spinner during slow operations."""
    if not _RICH_AVAILABLE or not sys.stdout.isatty():
        print(f"{message}...", end="", flush=True)
        try:
            yield
        finally:
            print(" done.")
        return
    try:
        from rich.live import Live
        from rich.spinner import Spinner as _RichSpinner
        with Live(_RichSpinner("dots", text=message), refresh_per_second=12):
            yield
    except Exception:
        print(f"{message}...", end="", flush=True)
        try:
            yield
        finally:
            print(" done.")


def prompt_text(message: str, default: str = "") -> str:
    # Fallback: if questionary is unavailable, use plain input()
    try:
        import questionary

        answer = questionary.text(message, default=default).ask()
        return default if answer is None else answer
    except Exception:
        prompt = f"{message} [{default}] " if default else f"{message} "
        try:
            answer = input(prompt)
            return answer if answer else default
        except (EOFError, KeyboardInterrupt):
            return default


def prompt_choice(message: str, choices: list[Choice], default: str = "") -> str:
    # Fallback: if questionary is unavailable, show numbered list and read raw input
    try:
        import questionary

        prompt_choices = [
            questionary.Choice(
                title=f"{choice.label}{f' - {choice.description}' if choice.description else ''}",
                value=choice.key,
            )
            for choice in choices
        ]
        answer = questionary.select(
            message, choices=prompt_choices, default=default or choices[0].key
        ).ask()
        return choices[0].key if answer is None else str(answer)
    except Exception:
        print(message)
        for i, c in enumerate(choices, 1):
            desc = f" - {c.description}" if c.description else ""
            print(f"  {i}. {c.label}{desc}")
        default_idx = 0
        if default:
            for i, c in enumerate(choices):
                if c.key == default:
                    default_idx = i
                    break
        prompt = f"Enter number or key [default {default_idx + 1}]: "
        for attempt in range(3):
            try:
                raw = input(prompt).strip()
                if not raw:
                    if default:
                        for c in choices:
                            if c.key == default:
                                return c.key
                    return choices[0].key
                try:
                    idx = int(raw) - 1
                    if 0 <= idx < len(choices):
                        return choices[idx].key
                except ValueError:
                    pass
                for c in choices:
                    if c.key == raw:
                        return c.key
                if attempt < 2:
                    print("Invalid selection, try again.")
            except (EOFError, KeyboardInterrupt):
                return choices[0].key
        return default if default else choices[0].key


def auto_detect_lean_mode() -> bool:
    """Return True if the terminal is non-interactive or WOMAN_LEAN is set."""
    import os
    return not sys.stdout.isatty() or os.environ.get("WOMAN_LEAN") == "1"


def danger_badge(score: float, reasons: list[str]) -> object:
    """Return a styled danger badge for destructive commands."""
    if score < 0.4 or not reasons:
        return _Text("") if _RICH_AVAILABLE else ""
    label = f"⚠  SAFETY: {', '.join(reasons)} (danger: {score:.2f})"
    if _RICH_AVAILABLE:
        style = "bold red" if score >= 0.85 else "bold yellow"
        return _Text(label, style=style)
    return label


def syntax_block(command: str) -> object:
    width = _terminal_width()
    if _RICH_AVAILABLE:
        return _Syntax(command, "bash", theme="monokai", word_wrap=True, code_width=width)
    return command


def prompt_command_action(
    command: str, danger_score: float = 0.0, danger_reasons: list[str] | None = None
) -> str:
    """Show 4-option action prompt for a generated command."""
    narrow = _terminal_width() < 80

    if danger_score >= 0.85:
        return prompt_choice(
            f"⚠  DANGEROUS COMMAND: {', '.join(danger_reasons or [])}",
            [
                Choice("review",  "⚠ Review",         "" if narrow else "inspect command + danger info"),
                Choice("execute", "▶ Execute anyway",  "" if narrow else "run despite danger"),
                Choice("edit",    "✏ Edit",            "" if narrow else "modify before running"),
                Choice("cancel",  "✕ Cancel",          "" if narrow else "do nothing"),
            ],
            default="review",
        )

    return prompt_choice(
        f"Command: {command}",
        [
            Choice("execute", "▶ Execute", "" if narrow else "run the command now"),
            Choice("copy",    "⎘ Copy",    "" if narrow else "copy to clipboard"),
            Choice("edit",    "✏ Edit",    "" if narrow else "modify before running"),
            Choice("cancel",  "✕ Cancel",  "" if narrow else "do nothing"),
        ],
        default="execute",
    )
