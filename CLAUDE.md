# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install with all features
pip install -e .[full]          # Rich UI + ML + test deps
pip install -e .[ui]            # Rich UI only (common dev install)
pip install -e .[test]          # pytest only

# Run tests
pytest tests/                   # full suite (162 tests)
pytest tests/test_engine.py     # single file
pytest tests/ -k "test_safety"  # by keyword

# Run the CLI directly
python -m woman_revamp "find all python files modified today"
woman "kill whatever is using port 3000"          # if installed
woman list --os linux                              # list known commands
woman explain "compress this directory"           # explain mode
woman --dry-run "remove all log files"            # show command, don't run
woman why "find modified files"                   # score breakdown
woman history                                     # last N queries
woman redo                                        # re-run last executed command
WOMAN_DEBUG=1 woman "find files"                  # verbose error output
WOMAN_SAFETY_OFF=1 woman "rm -rf /tmp/test"       # bypass danger warnings
WOMAN_LEAN=1 woman "show processes"               # no Rich UI (CI/pipe mode)
```

## Architecture

The scoring pipeline runs on every query:

```
Query
  → context.py       (shell history + active files as list[Path] + project signals)
  → engine.py        (tokenize → typo correct → synonym expand → pre-filter →
                       BM25 score → modifier flags → negation → template render)
  → ml/safety.py     (danger scoring — always runs, no ML model required)
  → [optional] ml/reranker.py (sklearn joblib model — disabled if model file absent)
  → cli.py           (4-option prompt: Execute / Copy / Edit / Cancel)
```

**Key scoring components in `engine.py`:**
- `TfIdfScorer` — BM25 scoring (k1=1.5, b=0.75); `avgdl` computed at init time
- `_scorer_cache` / `_vocab_cache` — module-level dicts keyed by `id(registry)`; cleared in `conftest.py` autouse fixture
- `_score_command()` — BM25 (×0.50) + name match (+0.15) + intent boost + context hints (+0.05) + signal bonuses (port/pid/days) + project signal boost (only when base score > 0.05) + negation penalty (−0.40)
- `_choose_template()` — priority order: rename slots → modifier flags → intent_map → days signal → directory/file heuristics → token key matching → scored fallback
- `fill_template()` — safely renders `{placeholder}` templates; returns `None` if required placeholders can't be filled
- `rank_candidates()` — pre-filters registry to entries with keyword overlap before full scoring; run shortcut (returns immediately for "run" intent + runnable files); pipe pattern check before scoring loop
- `MIN_CONFIDENCE = 0.30` — threshold; project signal boost only applied when base score > 0.05 to prevent zero-overlap commands from crossing threshold

**Registry structure** (`registry/`):
Each command spec is a `dict` with:
- `keywords` — terms for BM25 matching
- `templates` — `{template_name: "cmd --flag {placeholder}"}` dict
- `intent_map` — `{canonical_intent: template_name}` mapping

`shared.py` has cross-platform commands; `linux.py`, `macos.py`, `windows.py` have OS-specific ones. `get_registry(os_name)` merges shared + OS-specific + dynamic cache overlay. It's `@lru_cache`'d — call `get_registry.cache_clear()` in tests.

New registry modules:
- `runners.py` — `RUNNERS: dict[str, str]` (extension → interpreter) and `RUNNABLE_EXTENSIONS`
- `modifiers.py` — `MODIFIER_FLAGS` (word → flag) and `FLAGS_AWARE_COMMANDS`; modifier flags override intent_map in `_choose_template()`; flags are appended post-render only when not already present (checks combined flag sequences like `-Rni`)
- `pipes.py` — `PIPE_PATTERNS` pre-compiled regex list; matching queries inject a `pipe_shortcut` candidate at score=0.92 before the main scoring loop

**Context layer** (`context.py`):
- `get_active_files(cwd, max_files) -> list[Path]` — returns Path objects (not strings)
- `get_project_signals(cwd, active_files) -> dict[str, bool]` — detects git/docker/python/node/rust/go/make/venv via sentinel files
- `get_shell_history()` — most-recent command repeated once for recency weighting

**Dynamic registry** (`indexer/`):
- `cache.py` — loads/saves `~/.cache/woman/registry.json`; detects PATH changes via mtime snapshot
- `parser.py` — heuristic + optional AI parsing; `parse_tool_with_ai()` uses structured JSON schema prompt that includes man page text; AI responses cached in `~/.cache/woman/ai_cache.json` (7-day TTL, MD5-keyed by man page content)
- `providers.py` — pure urllib HTTP client for Ollama (streaming NDJSON), OpenAI, Anthropic, Gemini
- `ai_cache.py` — load/save/key helpers for AI response cache

**ML layer** (`ml/`):
- `safety.py` — always runs; `DANGER_PATTERNS` regex list with float scores; `calculate_danger_score()` respects `WOMAN_SAFETY_OFF=1`
- `reranker.py` — wraps `woman_revamp/ml/models/woman_reranker.joblib` (absent by default); `joblib` and `pandas` are lazy-imported
- `features.py` — builds DataFrame rows from query/candidate pairs for sklearn prediction

**UI layer** (`ui.py`):
- Rich is optional — guarded in try/except; `has_rich()` reflects actual availability
- `Console()` / `get_console()` return a `_PlainConsole` fallback if Rich is absent
- `auto_detect_lean_mode()` suppresses Rich when stdout is not a TTY or `WOMAN_LEAN=1`
- `confidence_label(score)` — High (≥0.80) / Moderate (≥0.55) / Low (≥0.30) / Very low
- `spinner(message)` — context manager; Rich Live if available, plain print fallback
- `syntax_block(command)` — passes `code_width=` (not `width=`) to Rich `Syntax`

**CLI** (`cli.py`):
- 4-option prompt: Execute / Copy / Edit / Cancel (normal); Review / Execute anyway / Edit / Cancel (dangerous ≥0.85)
- `_copy_to_clipboard()` — OS-native: macOS `pbcopy`, Wayland `wl-copy`, X11 `xclip`/`xsel`, Windows `clip`
- When reranker is unavailable (always currently), uses `candidates` already scored with `project_signals` — does NOT fall back to `call_local_registry()` which would lose context
- History recorded via `query_history.py` after every action; `woman history` / `woman redo` / `woman why` subcommands

**Query history** (`query_history.py`):
- `HistoryEntry` dataclass persisted to `~/.cache/woman/query_history.json` (max 500 entries)
- `append_history()`, `load_history(n)`, `last_executed()` — `last_executed()` finds most recent entry where `action == "execute"`

## Known Constraints

**ML model absent**: `woman_revamp/ml/models/woman_reranker.joblib` does not exist in the repo. `WomanReranker().available` is always `False`. The full reranking path is never exercised. Heuristic path handles all queries.

**Dynamic registry inflation**: Auto-indexed PATH tools can beat static registry entries for modifier-heavy queries (e.g., a tool with a `--verbose` template may outscore `ls` for "list files verbose"). The `tests/conftest.py` autouse fixture neutralizes this by patching `_load_dynamic_registry` to return `{}`. The conftest fixture also clears `_scorer_cache` and `_vocab_cache` alongside `get_registry.cache_clear()`.

**Scoring thresholds**: `MIN_CONFIDENCE = 0.30` in `engine.py`. Project signal boosts (+0.20–0.30) are only applied when the command's base score exceeds 0.05, preventing zero-vocabulary-overlap commands from crossing the threshold due to project context alone.

**`{flags}` slot**: `extract_modifier_flags()` fills a `{flags}` slot in `_default_command_slots()`. Flags are appended post-render to commands in `FLAGS_AWARE_COMMANDS` when not already present. Registry templates don't use `{flags}` directly — modifier words instead select named templates (e.g., "recursively" → "recursive" template) via `_choose_template()`.

## Environment Variables

| Variable | Effect |
|---|---|
| `WOMAN_SAFETY_OFF=1` | Skip all danger pattern checks |
| `WOMAN_LEAN=1` | Disable Rich UI (plain text output) |
| `WOMAN_DEBUG=1` | Include exception class in error messages |
