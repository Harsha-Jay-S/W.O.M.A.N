"""Tests for the risk label + command panel renderer."""

from __future__ import annotations

from woman_revamp.ui import render_command_panel, risk_label


def _plain(obj: object) -> str:
    """Render a Rich renderable (or plain string) to text for assertions."""
    try:
        from rich.console import Console

        buf = Console(record=True, width=100, no_color=True)
        buf.print(obj)
        return buf.export_text()
    except ImportError:
        return str(obj)


def test_risk_label_levels_render_their_words():
    assert "Low" in _plain(risk_label("Low"))
    assert "Moderate" in _plain(risk_label("Moderate"))
    assert "High" in _plain(risk_label("High"))


def test_render_command_panel_contains_command_and_restatement():
    panel = render_command_panel(
        restatement='Interpreting "all folders" as: archive each top-level folder',
        command='for d in */; do zip -r "${d%/}.zip" "$d"; done',
        risk_level="Low",
        overwrite=False,
        collisions=[],
    )
    text = _plain(panel)
    assert "Interpreting" in text
    assert "zip -r" in text
    assert "Low" in text


def test_render_command_panel_shows_overwrite_warning():
    panel = render_command_panel(
        restatement="Interpreting as: zip folders",
        command="zip -r archive.zip */",
        risk_level="Moderate",
        overwrite=True,
        collisions=["foo.zip", "bar.zip"],
    )
    text = _plain(panel)
    assert "foo.zip" in text
    assert "Overwrite" in text or "overwrite" in text
