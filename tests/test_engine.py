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


# ── Bug 4: "remove all log files" → apt beats find ────────────────────────────

def test_remove_log_files_returns_find_not_apt():
    """'remove all log files' must not surface apt — should be find or rm."""
    rendered = call_local_registry(
        "remove all log files",
        context="Current directory: /home/user\nFiles:",
        os_info="linux",
    )
    assert rendered is not None
    assert "apt" not in rendered, f"apt must not win for file removal: {rendered}"
    assert "find" in rendered or "rm" in rendered, f"expected find or rm, got: {rendered}"


def test_remove_log_files_uses_delete_template():
    """'remove all log files' should produce a find -delete command with *.log pattern."""
    rendered = call_local_registry(
        "remove all log files",
        context="Current directory: /home/user\nFiles:",
        os_info="linux",
    )
    assert rendered is not None
    assert "*.log" in rendered or ".log" in rendered, f"expected log pattern in: {rendered}"
    assert "delete" in rendered or "rm" in rendered, f"expected delete/rm in: {rendered}"


# ── Bug 5: "kill using port 3000" → pkill beats lsof ──────────────────────────

def test_kill_using_port_prefers_lsof():
    """'kill whatever is using port 3000' must map to lsof or fuser, not pkill."""
    rendered = call_local_registry(
        "kill whatever is using port 3000",
        context="Current directory: /home/user\nFiles:",
        os_info="linux",
    )
    assert rendered is not None
    # lsof with port, fuser by port, or ss — any is correct; pkill is NOT
    assert "pkill" not in rendered, f"pkill must not win for port-kill queries: {rendered}"
    assert "3000" in rendered, f"port number must appear in rendered command: {rendered}"


# ── Bug 6: auto-indexed PATH tools outrank curated commands ───────────────────
# Dynamic registry inflation: a PATH tool with bloated man-page keywords/templates
# (e.g. cd-paranoia, which carries dozens of --force-* flag templates) can outscore
# a curated static command. Dynamic-only entries are tagged "__dynamic__" at load
# time and penalised when the user did not name the tool itself.

import woman_revamp.engine as _engine
from woman_revamp.engine import (
    _score_command,
    TfIdfScorer,
    normalize_query,
    tokenize,
    expand_synonyms,
    extract_intent,
    extract_numbers,
    rank_candidates,
)
from woman_revamp.registry.shared import COMMANDS as _SHARED
from woman_revamp.registry.linux import COMMANDS as _LINUX


def test_dynamic_entry_penalized_unless_named():
    """An identical spec tagged __dynamic__ scores lower than the static version
    when the user did not name the tool, and the same when the tool IS named."""
    base = {
        "keywords": ["delete", "remove", "erase", "force", "recursive"],
        "templates": {"basic": "tool {path}"},
        "intent_map": {},
    }
    dyn = dict(base)
    dyn["__dynamic__"] = True

    scorer = TfIdfScorer({"tool": base})

    # Query does NOT name the tool → dynamic must be penalised below static.
    q = normalize_query("delete force recursive")
    toks = expand_synonyms(tokenize(q))
    intents = extract_intent(q)
    signals = extract_numbers(q)
    s_static, _ = _score_command("tool", base, toks, q, intents, [], signals, scorer)
    s_dyn, _ = _score_command("tool", dyn, toks, q, intents, [], signals, scorer)
    assert s_dyn < s_static, f"dynamic must be penalised: dyn={s_dyn} static={s_static}"

    # Query DOES name the tool → no penalty, scores equal.
    q2 = normalize_query("run tool now")
    toks2 = expand_synonyms(tokenize(q2))
    s_static2, _ = _score_command(
        "tool", base, toks2, q2, extract_intent(q2), [], extract_numbers(q2), scorer
    )
    s_dyn2, _ = _score_command(
        "tool", dyn, toks2, q2, extract_intent(q2), [], extract_numbers(q2), scorer
    )
    assert s_dyn2 == s_static2, f"named tool must not be penalised: {s_dyn2} vs {s_static2}"


def test_curated_static_beats_noisy_dynamic_tool(monkeypatch):
    """A dynamic PATH tool that outscores a curated command on raw keyword overlap
    must NOT win once the dynamic penalty is applied (user didn't name it)."""
    reg = {}
    reg.update(_SHARED)
    reg.update(_LINUX)
    # Junk dynamic tool with full keyword overlap → high raw score, would win pre-fix.
    reg["noisetool"] = {
        "__dynamic__": True,
        "keywords": ["delete", "remove", "erase", "force", "recursive", "root", "everything"],
        "templates": {"default": "noisetool"},
        "intent_map": {},
    }
    monkeypatch.setattr(_engine, "get_registry", lambda os_name=None: reg)

    results = rank_candidates(
        "delete everything in root recursively force", os_info="linux", limit=5
    )
    assert results, "expected ranked candidates"
    top = results[0]["command"]
    assert top != "noisetool", f"junk dynamic tool must not win: {results[:2]}"
    assert top in ("rm", "find"), f"expected curated rm/find on top, got {top}: {results[:2]}"


# ── Bug 7: quoted arg from shell-history context used as a file path ───────────

def test_shell_history_quoted_arg_not_used_as_path():
    """A quoted string from a prior shell command (e.g. `ollama run m "What is 2+2?"`)
    must NOT be extracted as the {path} of a generated command. Only quoted strings
    in the user's own query are paths."""
    ctx = (
        "Current directory: /home/u\n"
        "Files in directory:\n"
        'Recent shell history:\n'
        'ollama run qwen2.5-coder:7b --verbose "What is 2+2?"'
    )
    rendered = call_local_registry(
        "find all python files modified today", context=ctx, os_info="linux"
    )
    assert rendered is not None
    assert "2+2" not in rendered, f"history quoted arg leaked into path: {rendered}"
    assert "What is" not in rendered, f"history quoted arg leaked into path: {rendered}"
