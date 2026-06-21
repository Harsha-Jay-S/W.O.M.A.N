"""Standalone WOMAN banner with a horizontal 24-bit ANSI color gradient.

Self-contained (no dependency on ui.py). Warm Instagram palette, orange→magenta.
Render for review; wiring print_banner() into the CLI entry point is a later step.
"""

from __future__ import annotations

import os
import sys

WOMAN_BANNER = r"""
██╗    ██╗ ██████╗ ███╗   ███╗ █████╗ ███╗   ██╗
██║    ██║██╔═══██╗████╗ ████║██╔══██╗████╗  ██║
██║ █╗ ██║██║   ██║██╔████╔██║███████║██╔██╗ ██║
██║███╗██║██║   ██║██║╚██╔╝██║██╔══██║██║╚██╗██║
╚███╔███╔╝╚██████╔╝██║ ╚═╝ ██║██║  ██║██║ ╚████║
 ╚══╝╚══╝  ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝
"""

TAGLINE_BOX = r"""
╭──────────────────────────────────────────────────────────────────╮
│ ✦ w o m a n › the terminal, simplified ♥                         │
╰──────────────────────────────────────────────────────────────────╯
"""

# Gradient stops, left → right (warm Instagram: orange → magenta).
GRADIENT_STOPS = [
    (240, 148, 51),   # F09433
    (230, 104, 60),   # E6683C
    (220, 39, 67),    # DC2743
    (204, 35, 102),   # CC2366
    (188, 24, 136),   # BC1888
]

MUTED = (200, 200, 205)        # tagline text — secondary to the logo
SPARKLE = (240, 148, 51)       # ✦ — brightest (first) stop
HEART = (188, 24, 136)         # ♥ — last stop
BORDER_CHARS = set("╭─│╰╮╯")
RESET = "\x1b[0m"


def interpolate_gradient(
    stops: list[tuple[int, int, int]], t: float
) -> tuple[int, int, int]:
    """Linearly interpolate an RGB color along ``stops`` for ``t`` in [0, 1].

    Finds the segment ``t`` falls in and blends the two surrounding stops.
    """
    t = max(0.0, min(1.0, t))
    n = len(stops)
    if n == 1:
        return stops[0]
    seg = t * (n - 1)
    i = min(int(seg), n - 2)
    frac = seg - i
    a, b = stops[i], stops[i + 1]
    return (
        round(a[0] + (b[0] - a[0]) * frac),
        round(a[1] + (b[1] - a[1]) * frac),
        round(a[2] + (b[2] - a[2]) * frac),
    )


def _fg(rgb: tuple[int, int, int], ch: str) -> str:
    """Wrap a single character in a 24-bit ANSI foreground escape."""
    r, g, b = rgb
    return f"\x1b[38;2;{r};{g};{b}m{ch}"


def gradient_line(text: str, width: int, stops: list[tuple[int, int, int]]) -> str:
    """Color ``text`` left-to-right across a shared ``width``.

    Each character's color is keyed on its absolute column index over ``width``
    (the longest banner line), so every row shares one column→color mapping and
    the gradient stays vertically aligned. One reset is appended at the end.
    """
    parts: list[str] = []
    for i, ch in enumerate(text):
        t = i / (width - 1) if width > 1 else 0.0
        parts.append(_fg(interpolate_gradient(stops, t), ch))
    parts.append(RESET)
    return "".join(parts)


def _gradient_tagline_line(line: str) -> str:
    """Color one tagline-box line: border follows the gradient (over its own
    width), ✦/♥ get accent stops, all other text is muted off-white."""
    width = len(line)
    parts: list[str] = []
    for i, ch in enumerate(line):
        if ch == "✦":
            parts.append(_fg(SPARKLE, ch))
        elif ch == "♥":
            parts.append(_fg(HEART, ch))
        elif ch in BORDER_CHARS:
            t = i / (width - 1) if width > 1 else 0.0
            parts.append(_fg(interpolate_gradient(GRADIENT_STOPS, t), ch))
        else:
            parts.append(_fg(MUTED, ch))
    parts.append(RESET)
    return "".join(parts)


def render_banner() -> str:
    """Return the fully colored banner + tagline box as one string."""
    banner_lines = WOMAN_BANNER.strip("\n").splitlines()
    width = max((len(line) for line in banner_lines), default=0)
    out = [gradient_line(line, width, GRADIENT_STOPS) for line in banner_lines]

    tagline_lines = TAGLINE_BOX.strip("\n").splitlines()
    out.extend(_gradient_tagline_line(line) for line in tagline_lines)
    return "\n".join(out)


def _plain_banner() -> str:
    return WOMAN_BANNER.strip("\n") + "\n" + TAGLINE_BOX.strip("\n")


def print_banner() -> None:
    """Print the banner, respecting NO_COLOR, non-TTY output, and Windows."""
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR") is not None:
        print(_plain_banner())
        return

    if sys.platform == "win32":
        try:
            import colorama

            colorama.init()
        except ImportError:
            pass

    try:
        print(render_banner())
    except Exception:
        print(_plain_banner())


if __name__ == "__main__":
    print_banner()
