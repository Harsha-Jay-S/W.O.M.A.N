# W.O.M.A.N CLI — Comprehensive Improvement Plan

**Based on:** Full technical audit of `woman_revamp/` (42 files, ~3,620 LOC)  
**Audit date:** 2026-06-14

---

## Table of Contents

1. [UI/UX and Terminal Aesthetics](#1-uiux-and-terminal-aesthetics)
2. [Functional and Engine Enhancements](#2-functional-and-engine-enhancements)
3. [CLI Architecture and Best Practices](#3-cli-architecture-and-best-practices)
4. [Precision for This Specific Tool](#4-precision-for-this-specific-tool)
5. [Prioritized Roadmap](#5-prioritized-roadmap)

---

## 1. UI/UX and Terminal Aesthetics

### 1.1 Compact "Slim Purple" Layout

**Problem:** `show_banner()` in `cli.py:73` is called on every invocation and uses Rich `Panel` with a subtitle, adding 3+ lines of vertical padding. The `gradient_text()` function in `ui.py:28-29` is unused dead code. The confirmation prompt shows `syntax_block()` with a full `Syntax` widget (bottom padding + top padding).

**Solution:**
- Replace `Panel` banner with an inline gradient string — no borders, no padding:
  ```python
  def show_banner() -> None:
      console = Console()
      console.print("[bold #c084fc]woman[/bold #c084fc] [dim #e879f9]purple edition[/dim #e879f9]")
  ```
- Remove `Panel` and `subtitle` entirely.
- Show banner only on interactive TTY, not when `--json` or piped output is detected.
- Reduce `Syntax` widget to a flat `Text` with ANSI color (no theme wrapping) in confirm mode.

**Files affected:** `ui.py:32-37`, `cli.py:214-218`

### 1.2 TTY Detection and "Lean Mode"

**Problem:** CPR warnings appear in non-TTY environments (piped output, CI, `watch`). Rich's `Console` auto-detects width by querying cursor position, which fails on non-TTY.

**Solution:**
- Add `auto_detect_lean_mode()` at entrypoint:
  ```python
  def auto_detect_lean_mode() -> bool:
      return not sys.stdout.isatty() or os.environ.get("WOMAN_LEAN") == "1"
  ```
- If lean mode: use stdlib `print()` with plain text, skip `rich` imports entirely.
- Set `Console(force_terminal=False)` when not a TTY.
- Add `CI=true` / `WOMAN_LEAN=1` detection so CI runners get plain output.

**Files affected:** `ui.py` (new function), `cli.py` (guard around rich imports)

### 1.3 Rich Confirmation with Multi-Action Prompt

**Problem:** `cli.py:221-224` uses a simple `questionary.confirm("Execute this command?")` with only y/n. Users must abort and re-query to see alternatives or edit.

**Solution:** Replace with a `questionary.select` offering:
```
  ▶ Execute this command
    Edit command before running
    Explain what each flag does
    Show alternative candidates
    Show the man page
    Abort
```

```python
from .ui import Choice, prompt_choice

action = prompt_choice(
    f"Command: {command}",
    [
        Choice("execute", "Execute", "run the command now"),
        Choice("edit", "Edit", "open the command for editing"),
        Choice("explain", "Explain", "show what each flag does"),
        Choice("alternatives", "Alternatives", "show other candidates"),
        Choice("manual", "Manual", "show the real man page"),
        Choice("abort", "Abort", "do nothing"),
    ],
    default="execute",
)
```

If "edit" is chosen, spawn `$EDITOR` or use a `questionary.text` pre-filled with the command.

**Files affected:** `cli.py:219-231`, `ui.py:60-110`

---

## 2. Functional and Engine Enhancements

### 2.1 TF-IDF Style Scoring for Heuristic Engine

**Problem:** `engine.py:407-415` uses `SequenceMatcher` ratio (O(n²) per comparison) and simple substring checks. The scoring is ad-hoc integer bonuses with no normalization. `build_vocabulary()` builds a flat list but doesn't weight tokens by importance.

**Solution:**
- Replace raw `SequenceMatcher` with a simple TF-IDF scorer:
  ```python
  from collections import Counter
  import math

  class TfIdfScorer:
      def __init__(self, registry: dict):
          self.doc_freq: Counter = Counter()
          self.num_docs = len(registry)
          self.keyword_docs: dict[str, set[str]] = {}
          for name, spec in registry.items():
              tokens = set(tokenize(" ".join(spec.get("keywords", []))))
              for t in tokens:
                  self.doc_freq[t] += 1
                  self.keyword_docs.setdefault(t, set()).add(name)

      def score(self, query_tokens: list[str], cmd_tokens: list[str]) -> float:
          query_tf = Counter(query_tokens)
          score = 0.0
          for token, tf in query_tf.items():
              idf = math.log((self.num_docs + 1) / (self.doc_freq.get(token, 0) + 1)) + 1
              if token in cmd_tokens:
                  score += tf * idf
          return score / (len(query_tokens) or 1)
  ```
- Weight `intent_match` (+12) and `template_fillable` (+15) remain as score multipliers (×2.0) rather than flat additions, so they scale with query specificity.
- Normalize final scores to [0.0, 1.0] for better interop with `decide_action()` thresholds.

**Files affected:** `engine.py` — new `TfIdfScorer` class, refactor `_score_command`

### 2.2 Active File Prioritization in Context

**Problem:** `cli.py:167-168` grabs `sorted(p.name for p in cwd.iterdir())` limited to 200 entries — it's alphabetical, so stale files get equal billing with actively-edited ones.

**Solution:**
- Extract recently modified files (< 7 days) and recent project files (.py, .js, .ts, .md, .json) with mtime sorting:
  ```python
  from pathlib import Path
  import time

  NOW = time.time()
  DAY = 86400

  def _active_files(cwd: Path, max_files: int = 200) -> list[str]:
      all_entries = list(cwd.iterdir())
      # Recent files first, then files with extensions, then dirs
      def sort_key(p: Path) -> tuple:
          age = NOW - (p.stat().st_mtime if p.exists() else 0)
          is_recent = age < 7 * DAY
          has_ext = bool(p.suffix)
          return (0 if is_recent else 1, 0 if has_ext else 1, age)
      return [p.name for p in sorted(all_entries, key=sort_key)[:max_files]]
  ```
- Inject file mtime info into context string (e.g., "Recently modified: app.py, config.json").

**Files affected:** `context.py` (new `get_active_files()`), `cli.py:166-168`

### 2.3 Safety Score and Dry Run Mode

**Problem:** `ml/safety.py:22-30` applies a flat `DESTRUCTIVE_PENALTY = 0.35` for any `rm`/`mkfs`/`dd`/`shutdown`/`reboot`/`format` command. It doesn't distinguish `rm file` from `rm -rf /`. No dry-run flag exists.

**Solution:**
- Add fine-grained danger scoring:
  ```python
  DANGER_PATTERNS: list[tuple[str, float, str]] = [
      (r"\brm\s+-rf\s+/\s*$", 0.95, "Deleting root filesystem"),
      (r"\brm\s+-rf\b", 0.85, "Recursive force delete"),
      (r"\brm\b", 0.40, "Permanent file deletion"),
      (r"\bdd\b", 0.90, "Low-level disk write"),
      (r"\bmkfs\b", 0.95, "Filesystem creation — destructive"),
      (r"\bshutdown\b", 0.70, "System shutdown"),
      (r"\breboot\b", 0.60, "System reboot"),
      (r"\bformat\b", 0.90, "Format operation"),
      (r">\s*/dev/\w+", 0.85, "Writing to device directly"),
      (r"\|.*sudo", 0.50, "Piped to sudo — elevated risk"),
  ]

  def calculate_danger_score(command: str) -> tuple[float, list[str]]:
      reasons = []
      score = 0.0
      for pattern, penalty, reason in DANGER_PATTERNS:
          if re.search(pattern, command):
              score = max(score, penalty)
              reasons.append(reason)
      return min(score, 1.0), reasons
  ```
- Add `--dry-run` flag: shows the command with danger warnings and exits (no execution).
- Add `WOMAN_SAFETY_OFF=1` env var to disable all safety checks.
- Display danger badge in confirmation prompt:
  ```
  ⚠  DANGER: Deleting root filesystem (safety score: 0.95)
  $ rm -rf /
  ──────────────────────────────────────────────
  ```

**Files affected:** `ml/safety.py` (refactor), `cli.py` (add `--dry-run`), `ui.py` (danger badge rendering)

### 2.4 Explain Mode

**Problem:** No way to understand why a command was chosen or what each flag does. Users must manually run `man <command>` or visit explainshell.com.

**Solution:**
- Add `--explain` flag that prints a structured breakdown:
  ```
  $ woman --explain "find all python files modified in 7 days"

  Command:  find . -name "*.py" -mtime -7 -type f
  ─────────────────────────────────────────────────────
  Source:   Heuristic engine (confidence: 0.72)
  Intent:   find_files (score: +12)
  Context:  CWD has 3 .py files recently modified
  Slots:
    pattern  *.py     ← from "python files" in query
    days     7        ← from "7 days" in query
    kind     f        ← from "files" in query
  Flags:
    -name "*.py"      Filter by name pattern
    -mtime -7         Modified within the last 7 days
    -type f           Only files, not directories
  ```
- Implement an `explain_command()` function that traces back through the scoring pipeline, recording which signals contributed to the score.

**Files affected:** New `explain.py` module, `cli.py` (add `--explain` flag)

---

## 3. CLI Architecture and Best Practices

### 3.1 Proper Dependency Management (Remove Runtime Bootstrap)

**Problem:** `bootstrap.py:43-52` calls `os.execv()` after pip-installing packages at runtime. This is fragile, creates a new process, and can fail silently if pip is broken. The `pyproject.toml` already has `[ui]` extras, but there's no enforcement.

**Solution:**
- Remove `bootstrap.py` entirely.
- Make `rich` and `questionary` optional imports guarded by `try/except` at top of `ui.py`.
- Add `importlib.metadata` version check at startup:
  ```python
  def _warn_missing_extras():
      missing = []
      try:
          import rich  # noqa: F401
      except ImportError:
          missing.append("rich")
      try:
          import questionary  # noqa: F401
      except ImportError:
          missing.append("questionary")
      if missing:
          print(
              f"woman: install UI extras: pip install -e .[ui]",
              file=sys.stderr,
          )
          return False
      return True
  ```
- The CLI should function without rich/questionary using stdlib fallbacks (already partially handled in `ui.py:44-57` and `ui.py:60-110`).
- Update `pyproject.toml` with version pins:
  ```toml
  [project.optional-dependencies]
  ui = ["rich>=13.7.0", "questionary>=2.0.0"]
  ```

**Files affected:** `bootstrap.py` (delete), `entrypoint.py` (remove `ensure_runtime_dependencies`), `ui.py` (top-level try/except imports), `pyproject.toml` (version pins)

### 3.2 Standardized JSON Output Schema

**Problem:** `engine.py:782-791` returns ad-hoc dicts with keys `command`, `score`, `rendered`, `template`, `intent`. No confidence score, no source attribution, no OS info.

**Solution:** Standardize on:
```python
@dataclass
class WomanResult:
    command: str           # The base command name (e.g., "find")
    rendered: str          # The fully filled command string
    confidence_score: float  # Normalized 0.0-1.0
    source: str            # "heuristic" | "llm" | "ml_reranker"
    os_detected: str       # "linux" | "macos" | "windows"
    intent: str | None     # Matched intent
    template_key: str      # Which template was used
    heuristic_score: int   # Raw heuristic score
    ml_score: float | None # ML re-ranker score if available
    safety_score: float    # 0.0 (safe) to 1.0 (dangerous)
    danger_reasons: list[str]  # Why it's dangerous, if any
    candidates: list[dict]     # Alternative commands
```

When `--json` is used, emit `WomanResult` plus `{"meta": {"version": "...", "wall_time_ms": ...}}`.

**Files affected:** New `types.py` or `schemas.py`, `engine.py` (update `rank_candidates` return), `cli.py` (wrap JSON emission)

### 3.3 Zero-Config Operation

**Problem:** `cli.py:76-77` exits to the setup wizard if `CONFIG_FILE` doesn't exist. Users can't even run `woman --help` or `woman --list` without completing the wizard first.

**Solution:**
- Move wizard check to AFTER argument parsing. Non-query operations (`--help`, `--list`, `--json`, `--refresh-index`, `--dry-run`) should work with defaults.
- Create `WomanConfig.defaults()` that returns a usable config without a file:
  ```python
  @classmethod
  def defaults(cls) -> "WomanConfig":
      return cls(ui_mode="basic", ai_provider="none", index_mode="jit")
  ```
- If no config exists and a query is made, run the wizard. Otherwise use defaults.
- Log a single-line hint on first use: "Run `woman config` to customize AI providers and UI."

**Files affected:** `cli.py:76-77`, `config.py:63-64` (add `defaults()`), `wizard.py` (make non-blocking)

### 3.4 Subcommand Structure

**Problem:** Everything is a flag: `--list`, `--refresh-index`, `--index-tool`, `--json`, `--os`. No subcommands.

**Solution:** Migrate to a `subparser` model:
```
woman search "find large files"      # default action, same as today
woman list                           # --list
woman explain "ls -la"               # explain a command
woman config                         # run setup wizard
woman index refresh                  # --refresh-index
woman index docker                   # --index-tool docker
woman manual "find"                  # open man page for the command
woman shell-completions              # generate shell completions
```

Implementation sketch:
```python
parser = argparse.ArgumentParser(prog="woman")
subparsers = parser.add_subparsers(dest="subcommand")

# 'search' — default fallback
search = subparsers.add_parser("search", aliases=["s"])
search.add_argument("query", nargs="+")

# 'list'
list_ = subparsers.add_parser("list")
list_.add_argument("--os")

# 'explain'
explain = subparsers.add_parser("explain")
explain.add_argument("command", nargs="+")

# 'config'
subparsers.add_parser("config")

# 'index'
index = subparsers.add_parser("index")
index_sub = index.add_subparsers(dest="index_action")
index_sub.add_parser("refresh")
index_sub.add_parser("list")
index_tool = index_sub.add_parser("add")
index_tool.add_argument("tool")

# Backward compat: if no subcommand, treat as 'search'
args = parser.parse_args(argv)
if args.subcommand is None and " ".join(argv) not in {"--help", "-h"}:
    args.subcommand = "search"
```

Keep backward compatibility by treating bare flags like `--list` as their subcommand equivalents via wrapper logic.

**Files affected:** `cli.py` (full rewrite of `build_parser`), add `woman/commands/` package or inline dispatch

---

## 4. Precision for This Specific Tool

### 4.1 "Manual" Mode — Show the Real Man Page

**Problem:** Despite being named "woman" as a counterpart to "man", there's no way to see the actual man page from within the tool. The indexer reads man pages internally, but the user never sees them.

**Solution:**
- Add `--manual` flag (or `woman man <command>`) that opens `subprocess.run(["man", command])` in a pager.
- In the confirmation prompt (from 1.3), add a "Manual" option that runs `man <command>` and returns to the prompt afterward.
- In `--explain` mode (from 2.4), add a footer: "Run `woman manual find` for the full man page."

```python
def show_man_page(command_name: str) -> None:
    """Open the man page for a command, fall back to --help."""
    import subprocess
    import shutil
    if shutil.which("man") and subprocess.run(
        ["man", command_name], capture_output=True
    ).returncode == 0:
        subprocess.run(["man", command_name])
    else:
        subprocess.run([command_name, "--help"])
```

**Files affected:** New `manual.py` module, `cli.py` (add `--manual` flag / subcommand)

### 4.2 Shell Integration Script

**Problem:** `context.py:9-61` reads history files directly with fragile parsing for bash/zsh/fish/pwsh. The tool can't access the *last* command from the current shell session because history files are only written on shell exit (or with `history -a`).

**Solution:** Provide a shell function that passes `!!` as context:

```bash
# Add to ~/.bashrc or ~/.zshrc
woman() {
    if [ "$1" = "!!" ] || [ "$1" = "--last" ]; then
        local last_cmd=$(fc -ln -1)
        shift
        command woman --context "last command: $last_cmd" "$@"
    elif [ "$1" = "search" ]; then
        shift
        command woman "$@"
    else
        command woman "$@"
    fi
}
```

Also provide an installer:
```bash
woman shell-integration bash   # prints the above, or appends to ~/.bashrc
woman shell-integration zsh
woman shell-integration fish
```

The shell function also enables `woman !!` to ask "what did my last command do?" — a natural counterpart to explaining shell behavior.

**Files affected:** New `shell_integration.py` (generate bash/zsh/fish snippets), `cli.py` (add `shell-integration` subcommand), create `scripts/woman-shell.sh`

---

## 5. Prioritized Roadmap

### Phase 1 — Quick Wins (1-2 days)

| # | Item | Impact | Effort | Files |
|---|---|---|---|---|
| 1 | **Compact banner** — remove Panel padding | Medium | 15 min | `ui.py:32-37` |
| 2 | **Zero-config operation** — skip wizard for --help/--list | High | 1 hr | `cli.py:76-77`, `config.py` |
| 3 | **TTY detection** — suppress CPR warnings in CI | High | 30 min | `ui.py`, `cli.py` |
| 4 | **Safety score** — danger badge on `rm -rf /` | High | 2 hr | `ml/safety.py`, `cli.py` |
| 5 | **--dry-run flag** | Medium | 30 min | `cli.py` |

### Phase 2 — Core Rewrites (3-5 days)

| # | Item | Impact | Effort | Files |
|---|---|---|---|---|
| 6 | **TF-IDF scorer** — replace SequenceMatcher | High | 4 hr | `engine.py` |
| 7 | **Remove runtime bootstrap** | Medium | 1 hr | `bootstrap.py`, `entrypoint.py` |
| 8 | **Active file prioritization** | Medium | 2 hr | `context.py`, `cli.py` |
| 9 | **Standardized JSON schema** | Medium | 2 hr | `types.py`, `engine.py`, `cli.py` |

### Phase 3 — Surface Polish (2-3 days)

| # | Item | Impact | Effort | Files |
|---|---|---|---|---|
| 10 | **Rich confirmation with multi-action** | High | 3 hr | `cli.py:219-231`, `ui.py` |
| 11 | **Explain mode** | High | 4 hr | `explain.py`, `cli.py` |
| 12 | **Manual mode** | Medium | 1 hr | `manual.py`, `cli.py` |

### Phase 4 — Architecture (3-5 days)

| # | Item | Impact | Effort | Files |
|---|---|---|---|---|
| 13 | **Subcommand structure** | High (architectural) | 6 hr | `cli.py` full rewrite |
| 14 | **Shell integration script** | Medium | 2 hr | `shell_integration.py`, `scripts/` |

---

## Summary of New Files to Create

| File | Purpose |
|---|---|
| `woman_revamp/types.py` | `WomanResult` dataclass, shared schemas |
| `woman_revamp/explain.py` | Trace-based command explanation |
| `woman_revamp/manual.py` | Man page viewer |
| `woman_revamp/shell_integration.py` | Bash/zsh/fish integration generator |
| `woman_revamp/commands/search.py` | Search subcommand handler |
| `woman_revamp/commands/config.py` | Config subcommand handler |
| `woman_revamp/commands/index.py` | Index subcommand handler |
| `scripts/woman-shell.sh` | Shell function for `!!` capture |

## Files to Modify

| File | Changes |
|---|---|
| `ui.py` | Compact banner, TTY detection, danger badge, multi-action prompt |
| `cli.py` | Subcommands, --dry-run, --explain, --manual, zero-config, multi-action confirm |
| `engine.py` | TF-IDF scorer, normalised scores, source attribution |
| `ml/safety.py` | Granular danger scoring, WOMAN_SAFETY_OFF env var |
| `ml/features.py` | Add `has_chmod`, `has_redirect`, `danger_score` features |
| `context.py` | Active file prioritization by mtime |
| `config.py` | `defaults()` classmethod, zero-config support |
| `bootstrap.py` | DELETE — remove runtime pip install |
| `entrypoint.py` | Remove `ensure_runtime_dependencies` |
| `pyproject.toml` | Version pins, new optional deps |

## Files to Delete

| File | Reason |
|---|---|
| `bootstrap.py` | Replaced by proper extras_require + guarded imports |

---

## Test Plan

| Test File | New Tests Needed |
|---|---|
| `tests/test_engine.py` | TF-IDF scoring, normalized scores, confidence |
| `tests/test_safety.py` | Danger scoring for rm -rf /, dd, mkfs |
| `tests/test_explain.py` | Explain output structure |
| `tests/test_cli.py` | Subcommand dispatch, zero-config, --dry-run |
| `tests/test_ui.py` | TTY fallback, compact banner |
| `tests/test_json_schema.py` | Standardized schema validation |

---

## Design Principles for Implementation

1. **Backward compatibility first** — old flags (`--list`, `--json`, `--refresh-index`) must keep working during Phase 1-2. Deprecation warnings can come in Phase 4.
2. **Graceful degradation** — all UI enhancements must have a stdlib fallback. Rich/questionary are never required for basic operation.
3. **No new heavy dependencies** — TF-IDF scorer uses `collections.Counter` and `math` only. No scikit-learn dependency for scoring core.
4. **Preserve the "woman" identity** — the purple theme, the name parity with `man`, and the "do one thing well" philosophy stay. The tool translates NL to commands — it doesn't need to become a shell.
