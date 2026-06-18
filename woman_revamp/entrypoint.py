"""Console-script entrypoint with friendly error handling."""

from __future__ import annotations

import sys


def _print_user_error(exc: BaseException) -> None:
    try:
        from rich.console import Console

        Console(stderr=True).print(f"[bold red]Error:[/bold red] {exc}")
    except Exception:
        print(f"Error: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    try:
        from .cli import main as cli_main

        return cli_main(argv)
    except SystemExit:
        raise
    except Exception as exc:
        from .errors import render_user_error

        _print_user_error(render_user_error(exc))
        return 1
