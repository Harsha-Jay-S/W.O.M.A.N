# Woman CLI — Prioritized Maintenance Plan

## P0 — Security (fix immediately)

### 1. `cli.py:167` — Shell injection via `subprocess.run(command, shell=True)`
The `command` variable (from rendered template) is passed to `subprocess.run` with `shell=True`. User input flows through `query` → template rendering → shell execution.
**Fix:** Replace `subprocess.run(command, shell=True)` with `subprocess.run(shlex.split(command))` and remove `shell=True`. This renders shell injection impossible.

### 2. `tests/test_engine.py:19` — Hardcoded `/home/jayharsha` path
Will fail on any other machine.
**Fix:** Replace with synthetic context string (no real path needed — the test only validates template selection logic).

## P1 — Correctness (fix next sprint)

### 3. `cli.py:146` — `history` shadows built-in `history()`
Renaming to `cmd_history` prevents subtle bugs if `history` is ever used as a callable.

### 4. `ui.py:24-25` — `has_rich()` always returns `True`
Callers that gate on this will never take the fallback path.
**Fix:** Check `sys.stdout.isatty()` and try-except import of `rich`.

### 5. `cli.py:22-23` — Module-level imports of `Console` and `questionary`
These heavy imports run at module load time, even for `--json` or `--list` subcommands that never use them. Also breaks test patching.
**Fix:** Move `from rich.console import Console` and `import questionary` inside `main()`. (Audit incorrectly called these "local inside main()"; they are module-level.)

### 6. `context.py:33-46` — Fish shell history parsed incorrectly
Fish history files use YAML format (`- cmd: ...`), not line-per-command. The current code strips `- cmd:` prefix but reads fish_history as flat lines. Many lines like `when: ...` are skipped but the YAML structure means multi-line commands and metadata will corrupt the output.
**Fix:** Skip fish history file or add YAML parser fallback for fish format.

### 7. `cli.py:71` — `main()` is 106 lines (target: ≤50)
Should extract: `_ensure_config()` (setup + registry refresh), `_handle_refresh_flags()`, `_gather_context()`, `_execute_command()`.

### 8. `pyproject.toml:11` — `dependencies = []` with no core deps
`rich` and `questionary` are listed as `[project.optional-dependencies] ui` but are imported unconditionally at module level (`ui.py`, `cli.py`). If a user runs `pip install woman-revamp` without the `[ui]` extra, it crashes at import time.
**Fix:** Move `rich` and `questionary` into core `dependencies` (since they're required), or add guard imports.

## P2 — Coverage (implement before any feature work)

### 9. Tests missing for every module
| Module | LOC | Tests | Status |
|--------|-----|-------|--------|
| `cli.py` | 177 | 0 | **Write tests** for `main()`, `build_parser()`, error paths, `--json`, `--list`, `--refresh-index`, `--index-tool` |
| `config.py` | 62 | 0 | **Write tests** for `WomanConfig.load()/save()`, `ensure_directories()`, `read_json/write_json` |
| `context.py` | 46 | 0 | **Write tests** for `get_shell_history()` with mock files |
| `bootstrap.py` | 45 | 0 | **Write tests** for `missing_ui_dependencies()`, `prompt_install_missing()` |
| `wizard.py` | 69 | 0 | **Write tests** for `run_setup()` questions |
| `indexer/parser.py` | 215 | 2 | **Add tests** for `_capture()`, `extract_sections()`, `_keywords_from_sections()`, `_templates_from_text()` |
| `indexer/cache.py` | 81 | 0 | **Write tests** for `refresh_registry_cache()`, `load_cached_registry()` |
| `indexer/scanner.py` | 48 | 0 | **Write tests** for `discover_path_tools()`, `snapshot_path_state()` |
| `indexer/providers.py` | 111 | 0 | **Write tests** for `build_provider_payload()` all 4 providers |
| `engine.py` | 670 | 4 | **Add tests** for empty query, unicode, special chars, large input, edge cases |

### 10. `tests/__init__.py` missing
Prevents `pytest` from discovering tests properly in some configurations.
**Fix:** Create empty `tests/__init__.py`.

### 11. `tests/test_parser.py:12-13` — Requires real `man` command
`test_parse_tool_uses_real_man_page` and `test_capture_limits_real_man_page` call out to system `man`. This breaks CI without `man`.
**Fix:** Mock `_capture()` or `_help_text()` to return canned man output.

## P3 — Performance

### 12. `engine.py:131` — `build_vocabulary()` recomputed per `rank_candidates()` call
`rank_candidates()` (called on every query) builds the vocabulary from scratch by iterating the full registry. Since `get_registry()` is already `@lru_cache`'d, `build_vocabulary` should be too.
**Fix:** `@lru_cache(maxsize=1)` on `build_vocabulary()` with the registry dict converted to a hashable tuple.

## P4 — Repository hygiene

### 13. 17 `__pycache__/` directories tracked in git
`.gitignore` has `__pycache__/` but these were committed before the rule existed.
**Fix:** `git rm -r --cached */__pycache__` and all `.pyc` files.

### 14. `py.typed` marker missing
Needed for PEP 561 compliance so type checkers resolve annotations.
**Fix:** `touch woman_revamp/py.typed` (the package root, which is the `woman/` directory).

### 15. `requirements.txt` is redundant
Dependencies are in `pyproject.toml`; `requirements.txt` duplicates them and will drift.
**Fix:** Delete `requirements.txt`.

### 16. `indexer/providers.py:81` — ollama timeout of 180s
A CLI tool blocking for 3 minutes on a network call is unacceptable.
**Fix:** Reduce to 30s with a note. Or remove the special-case and use 15s for all providers.
