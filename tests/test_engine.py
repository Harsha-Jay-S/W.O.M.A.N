from woman_revamp.config import WomanConfig
from woman_revamp.engine import call_local_registry, extract_numbers, fill_template
from woman_revamp.ui import confidence_label_plain


def test_fill_template_requires_days():
    assert (
        fill_template(
            "find {path} -type {kind} -mtime {days}", {"path": ".", "kind": "d"}
        )
        is None
    )


def test_fill_template_renders_when_complete():
    assert (
        fill_template(
            "find {path} -type {kind} -mtime {days}",
            {"path": ".", "kind": "d", "days": "7"},
        )
        == "find . -type d -mtime 7"
    )


def test_directory_query_prefers_directory_find():
    rendered = call_local_registry(
        "find all directories in this folder",
        context="Current directory: /home/jayharsha\nFiles:",
        os_info="linux",
    )
    assert rendered == "find /home/jayharsha -type d"


def test_config_defaults_to_300_lines():
    assert WomanConfig().man_page_limit == 300


# ── Bug 1: "today" / "yesterday" / "this week" not recognised as days ─────────

def test_extract_numbers_today_maps_to_minus_one_day():
    signals = extract_numbers("find python files modified today")
    assert "days" in signals, "expected 'days' signal from 'today'"
    assert signals["days"] == "-1"


def test_extract_numbers_yesterday_maps_to_minus_two_days():
    signals = extract_numbers("show files changed yesterday")
    assert "days" in signals, "expected 'days' signal from 'yesterday'"
    assert signals["days"] == "-2"


def test_extract_numbers_this_week_maps_to_minus_seven_days():
    signals = extract_numbers("find logs created this week")
    assert "days" in signals, "expected 'days' signal from 'this week'"
    assert signals["days"] == "-7"


def test_extract_numbers_numeric_days_unchanged():
    """Existing numeric pattern must keep working."""
    signals = extract_numbers("files older than 30 days")
    assert signals.get("days") == "30"


# ── Bug 2: "python files" should set -name '*.py' in find template ─────────────

def test_find_python_files_uses_name_pattern():
    rendered = call_local_registry(
        "find all python files",
        context="Current directory: /home/user\nFiles:",
        os_info="linux",
    )
    assert rendered is not None, "expected a rendered command"
    assert "-name" in rendered
    assert "*.py" in rendered


def test_find_javascript_files_uses_name_pattern():
    rendered = call_local_registry(
        "find all javascript files",
        context="Current directory: /home/user\nFiles:",
        os_info="linux",
    )
    assert rendered is not None
    assert "-name" in rendered
    assert "*.js" in rendered


def test_find_python_files_modified_today_combines_mtime_and_name():
    rendered = call_local_registry(
        "find python files modified today",
        context="Current directory: /home/user\nFiles:",
        os_info="linux",
    )
    assert rendered is not None
    assert "-name" in rendered
    assert "*.py" in rendered
    assert "-mtime" in rendered


# ── Bug 3: confidence_label boundary verification ─────────────────────────────

def test_confidence_label_low_for_0_38():
    assert confidence_label_plain(0.38) == "● Low"


def test_confidence_label_moderate_at_boundary_0_55():
    assert confidence_label_plain(0.55) == "● Moderate"


def test_confidence_label_high_at_boundary_0_80():
    assert confidence_label_plain(0.80) == "● High"


def test_confidence_label_very_low_below_threshold():
    assert confidence_label_plain(0.29) == "● Very low"


def test_confidence_label_not_high_below_0_80():
    """0.79 must not show High — catches off-by-one on the 0.80 boundary."""
    assert confidence_label_plain(0.79) != "● High"
