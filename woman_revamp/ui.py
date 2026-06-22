"""Terminal UI helpers for woman_revamp."""

from __future__ import annotations

import shutil
import sys
from contextlib import contextmanager
from dataclasses import dataclass

try:
    from rich.console import Console as _Console
    from rich.console import Group as _Group
    from rich.panel import Panel as _Panel
    from rich.syntax import Syntax as _Syntax
    from rich.text import Text as _Text
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False

# Accent colors pulled from the banner gradient (orange → magenta) so the
# interactive UI shares the brand palette.
ACCENT_ORANGE = "#f09433"
ACCENT_PINK = "#cc2366"
ACCENT_MAGENTA = "#bc1888"

_RISK_STYLES = {
    "High": "bold red",
    "Moderate": "bold yellow",
    "Low": "bold green",
}


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


def show_banner() -> None:
    """Render the WOMAN banner (warm gradient renderer in banner.py)."""
    from .banner import print_banner

    print_banner()


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
        # Single, brand-colored selection indicator: recolor the row highlight
        # to the banner gradient and replace the default `»` with a thin marker.
        style = None
        try:
            from questionary import Style as _QStyle

            style = _QStyle([
                ("qmark", f"fg:{ACCENT_ORANGE} bold"),
                ("question", "bold"),
                ("pointer", f"fg:{ACCENT_MAGENTA} bold"),
                ("highlighted", f"fg:{ACCENT_MAGENTA} bold"),
                ("selected", f"fg:{ACCENT_PINK}"),
                ("answer", f"fg:{ACCENT_PINK} bold"),
            ])
        except Exception:
            style = None

        select_kwargs: dict[str, object] = {
            "choices": prompt_choices,
            "default": default or choices[0].key,
        }
        if style is not None:
            select_kwargs["style"] = style
            select_kwargs["pointer"] = "›"
        try:
            answer = questionary.select(message, **select_kwargs).ask()
        except TypeError:
            # Older questionary without style/pointer kwargs.
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


def risk_label(level: str) -> object:
    """Return a styled risk badge (``● Low`` / ``● Moderate`` / ``● High``)."""
    text = f"● {level}"
    if _RICH_AVAILABLE:
        return _Text(text, style=_RISK_STYLES.get(level, "dim"))
    return text


def render_command_panel(
    restatement: str,
    command: str,
    risk_level: str,
    overwrite: bool = False,
    collisions: list[str] | None = None,
) -> object:
    """Render the restated intent + command + risk as one bordered panel.

    Falls back to a plain multi-line string when Rich is unavailable.
    """
    collisions = collisions or []
    if not _RICH_AVAILABLE:
        lines = [f"Interpreting as: {restatement}" if restatement else "", command, f"Risk: ● {risk_level}"]
        if overwrite and collisions:
            lines.append(f"⚠ Overwrites: {', '.join(collisions)}")
        return "\n".join(line for line in lines if line)

    rows: list[object] = []
    if restatement:
        rows.append(_Text(restatement, style="italic"))
        rows.append(_Text(""))
    rows.append(syntax_block(command))
    rows.append(_Text(""))
    risk_line = _Text("Risk: ", style="dim")
    risk_line.append_text(risk_label(risk_level))
    rows.append(risk_line)
    if overwrite and collisions:
        rows.append(_Text(f"⚠ Overwrites: {', '.join(collisions)}", style="bold yellow"))
    return _Panel(
        _Group(*rows),
        border_style=ACCENT_PINK,
        padding=(1, 2),
        title="[dim]woman[/dim]",
        title_align="left",
    )


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
                Choice("edit",    "✎ Edit",            "" if narrow else "modify before running"),
                Choice("cancel",  "✕ Cancel",          "" if narrow else "do nothing"),
            ],
            default="review",
        )

    return prompt_choice(
        "Choose an action",
        [
            Choice("execute", "▶ Execute", "" if narrow else "run the command now"),
            Choice("copy",    "⧉ Copy",    "" if narrow else "copy to clipboard"),
            Choice("edit",    "✎ Edit",    "" if narrow else "modify before running"),
            Choice("cancel",  "✕ Cancel",  "" if narrow else "do nothing"),
        ],
        default="execute",
    )
