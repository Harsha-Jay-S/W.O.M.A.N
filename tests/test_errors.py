from __future__ import annotations

import sys
from pathlib import Path
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from woman_revamp.errors import WomanError, render_user_error


def test_render_user_error_for_custom_error():
    message = render_user_error(
        WomanError(
            action="refresh the registry",
            reason="the cache file is locked",
            hint="Try again in a moment.",
        )
    )
    assert "could not refresh the registry" in message
    assert "locked" in message


def test_render_user_error_for_url_error():
    message = render_user_error(URLError("connection refused"))
    assert "could not contact the AI provider" in message


def test_render_user_error_for_unknown_exception():
    message = render_user_error(RuntimeError("boom"))
    assert "unexpected problem" in message
