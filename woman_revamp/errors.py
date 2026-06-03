"""User-facing error formatting for woman_revamp."""

from __future__ import annotations

from dataclasses import dataclass
import os
import subprocess
from typing import Any
from urllib.error import URLError


@dataclass(frozen=True)
class WomanError(RuntimeError):
    """A friendly error intended to be shown directly to users."""

    action: str
    reason: str
    hint: str = ""

    def message(self) -> str:
        base = f"woman could not {self.action} because {self.reason}."
        if self.hint:
            return f"{base} {self.hint}"
        return base


def _with_article(text: str) -> str:
    lowered = text.strip().lower()
    if not lowered:
        return text
    if lowered[0] in "aeiou":
        return f"an {text}"
    return f"a {text}"


def friendly_message(exc: BaseException) -> str:
    if isinstance(exc, WomanError):
        return exc.message()
    if isinstance(exc, PermissionError):
        return "woman could not continue because it does not have permission to access the required file or folder."
    if isinstance(exc, FileNotFoundError):
        return "woman could not continue because a required file or command was not found."
    if isinstance(exc, URLError):
        return "woman could not contact the AI provider because the endpoint was unreachable. Check that the service is running and the URL is correct."
    if isinstance(exc, subprocess.CalledProcessError):
        return f"woman could not complete the command because it exited with code {exc.returncode}."
    if isinstance(exc, TimeoutError):
        return "woman could not finish because an operation timed out. Try again or use a smaller input."
    if isinstance(exc, OSError):
        detail = getattr(exc, "strerror", "an operating system error") or "an operating system error"
        return f"woman could not continue because of {_with_article(str(detail))}."
    return "woman ran into an unexpected problem. Try again or run with WOMAN_DEBUG=1 for details."


def render_user_error(exc: BaseException) -> str:
    message = friendly_message(exc)
    if os.environ.get("WOMAN_DEBUG") == "1":
        return f"{message} [{exc.__class__.__name__}: {exc}]"
    return message
