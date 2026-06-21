"""Sanity tests for the standalone gradient banner."""

from woman_revamp.banner import (
    GRADIENT_STOPS,
    RESET,
    gradient_line,
    interpolate_gradient,
)


def test_interpolate_endpoints_and_middle():
    assert interpolate_gradient(GRADIENT_STOPS, 0.0) == GRADIENT_STOPS[0]
    assert interpolate_gradient(GRADIENT_STOPS, 1.0) == GRADIENT_STOPS[-1]
    # 5 stops → t=0.5 lands exactly on the middle stop.
    assert interpolate_gradient(GRADIENT_STOPS, 0.5) == GRADIENT_STOPS[2]


def test_interpolate_clamps_out_of_range():
    assert interpolate_gradient(GRADIENT_STOPS, -1.0) == GRADIENT_STOPS[0]
    assert interpolate_gradient(GRADIENT_STOPS, 2.0) == GRADIENT_STOPS[-1]


def test_gradient_line_starts_at_first_stop_and_resets_once():
    line = gradient_line("HELLO", width=5, stops=GRADIENT_STOPS)
    assert line.startswith("\x1b[38;2;240;148;51m")  # first stop at column 0
    assert line.count(RESET) == 1                      # single reset at end
    assert line.endswith(RESET)
