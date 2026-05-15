"""Terminal UI helpers for woman_revamp."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text


PURPLE_STOPS = ["#7c3aed", "#8b5cf6", "#a855f7", "#c084fc", "#e879f9"]


@dataclass(frozen=True)
class Choice:
    key: str
    label: str
    description: str = ""


def has_rich() -> bool:
    return True


def gradient_text(lines: Iterable[str]) -> str:
    return "\n".join(lines)


def show_banner() -> None:
    console = Console()
    text = Text()
    text.append("woman", style="bold #c084fc")
    text.append(" setup", style="#e879f9")
    console.print(Panel(text, border_style="#8b5cf6", subtitle="purple edition"))


def show_progress(message: str) -> None:
    Console().print(f"[bold #c084fc]{message}[/bold #c084fc]")


def prompt_text(message: str, default: str = "") -> str:
    import questionary

    answer = questionary.text(message, default=default).ask()
    return default if answer is None else answer


def prompt_choice(message: str, choices: list[Choice], default: str = "") -> str:
    import questionary

    prompt_choices = [questionary.Choice(title=f"{choice.label}{f' - {choice.description}' if choice.description else ''}", value=choice.key) for choice in choices]
    answer = questionary.select(message, choices=prompt_choices, default=default or choices[0].key).ask()
    return choices[0].key if answer is None else str(answer)


def syntax_block(command: str) -> Syntax:
    return Syntax(command, "bash", theme="monokai", word_wrap=True)
