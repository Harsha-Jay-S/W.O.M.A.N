# `woman`
### Working Omniscient Manager of Actual Needs

> The AI-powered counterpart to the Linux `man` command. Because if `man` exists, `woman` should too.

```bash
$ woman extract this gzip file
$ woman find all python files modified in the last 24 hours
$ woman kill whatever is hogging port 3000
```

---

## Why this exists

It was late. I forgot an `nmap` flag. Again. I typed `man nmap`, got my answer, moved on.

There's a `man` command. There's no `woman` command. Not for any real reason — nobody just... did it.

So I built one over a weekend. Mostly for fun. Partly out of spite.

`woman` skips the manual page entirely. She looks at your current directory, your shell history, and your OS, then prints the exact command you need. You decide whether to run it.

---

## What it does

You type what you want in plain English. `woman` grabs context first — your OS, the files in your current directory, your last 5 shell commands — and builds a command for your exact setup.

- **No SDK dependencies.** Uses native Python `urllib` to talk to LLMs. Boots fast.
- **Optional rich UI.** Uses `rich` and `questionary` for a purple terminal interface (installed via the `[ui]` extra). If they're missing, it falls back to plain text automatically — no prompt, no crash.
- **Reads your `$PATH`.** It knows what tools you actually have.
- **Parses man pages on the fly.** If a tool isn't indexed, it pulls the first 300 lines of the man page and works from there — heuristics or AI, depending on your config.
- **Works offline.** No LLM provider set up? It falls back to local heuristic matching.

---

## Installation

```bash
git clone https://github.com/Harsha-Jay-S/W.O.M.A.N.git
cd W.O.M.A.N
bash install.sh
```

Or with `pip`:
```bash
pip install -e .[ui]
```

Then run setup:
```bash
woman config
```

You'll pick:
* **UI mode:** Rich (purple gradients) or Basic.
* **AI provider:** Ollama, OpenAI, Anthropic, Gemini, or None.
* **Indexing mode:** JIT (recommended) or Batch.

Settings go in `~/.config/woman/config.json`.

---

## Usage

`woman` watches your `$PATH`. Install something new and she'll ask if you want to refresh.

```bash
woman --list                            # List all indexed tools
woman --refresh-index                   # Force refresh the PATH cache
woman --index-tool docker               # Manually index a specific tool
woman "undo my last git commit"         # Normal usage
woman --json "what is using port 8080"  # Output raw scoring JSON
```

### Subcommands

The bare `woman "query"` form still works; these are the explicit subcommands:

| Command | What it does |
|---|---|
| `woman search "<query>"` | Translate a query (alias: `woman s`) |
| `woman explain "<query>"` | Show the command + flag breakdown, don't run it |
| `woman why "<query>"` | Scoring breakdown for debugging matches |
| `woman manual <cmd>` | Show the man page (alias: `woman man`) |
| `woman list` | List indexed commands |
| `woman index refresh \| list \| add <tool>` | Manage the PATH index |
| `woman history` / `woman redo` | Recent queries / re-run last executed |
| `woman config` | Run the setup wizard |
| `woman shell-integration [bash\|zsh\|fish]` | Print shell hook code |

Flags: `--dry-run` (show, don't run), `-y`/`--yes` (run without the confirmation prompt — **required** for piped/non-interactive use; dangerous commands are still refused), `--json` (raw scoring), `--list`, `--refresh-index`, `--index-tool <tool>`.

> Safety: before running, `woman` shows a panel that **restates how it interpreted you** (e.g. "zip *each top-level folder into its own archive* — edit if you meant one combined archive"), a **risk level** computed from the actual command, and an **overwrite warning** if the output files already exist. Run interactively, it always asks before executing. Run piped or in a script, it prints the command and does nothing unless you pass `--yes` (dangerous commands are refused even then).

### Supported AI providers
- **`ollama`** — local models at `http://localhost:11434`. No API key, runs on your machine.
- **`openai`** — GPT-4o, etc.
- **`anthropic`** — Claude.
- **`gemini`** — Google Gemini.
- **`none`** — offline heuristics only.

---

## How it works

```text
woman "your query"
       │
       ▼
 Context Gathering
 ┌─────────────────────────────────────────────┐
 │ OS + distro                                 │
 │ Current directory path                      │
 │ Files in directory                          │
 │ Last 5 shell commands (bash/zsh/fish/pwsh)  │
 └─────────────────────────────────────────────┘
       │
       ▼
 Registry & PATH Matching
 ┌─────────────────────────────────────────────┐
 │ Scans ~/.cache/woman/ registry for matches  │
 │ Identifies required tools (e.g., tar, find) │
 └─────────────────────────────────────────────┘
       │
       ▼
 JIT Parsing & LLM/Heuristics
 ┌─────────────────────────────────────────────┐
 │ If tool is un-indexed, reads first 300      │
 │ lines of `man` or `--help`.                 │
 │ Passes context + man snippet to LLM         │
 │ via urllib HTTP client.                     │
 └─────────────────────────────────────────────┘
       │
       ▼
 Print command in purple UI
       │
       ▼
 Confirm: Execute / Copy / Edit / Cancel
 (dangerous command → Review / Execute anyway / Edit / Cancel)
       │
       ▼
 subprocess → your shell → output
```

## Architecture

```text
User Query
       │
       ▼
 Context Collector
 ┌─────────────────────────────────────────────┐
 │ OS, cwd contents, shell history             │
 └─────────────────────────────────────────────┘
       │
       ▼
 Tool Discovery Layer
 ┌─────────────────────────────────────────────┐
 │ PATH scanning + local registry              │
 └─────────────────────────────────────────────┘
       │
       ▼
 Command Knowledge Layer
 ┌─────────────────────────────────────────────┐
 │ man pages / --help / JIT parsing            │
 └─────────────────────────────────────────────┘
       │
       ▼
 ML Re-ranker
 ┌─────────────────────────────────────────────┐
 │ Local heuristic scoring & intent matching   │
 └─────────────────────────────────────────────┘
       │
       ▼
 Provider Layer
 ┌─────────────────────────────────────────────┐
 │ Ollama / OpenAI / Gemini / Anthropic        │
 │ or offline fallback                         │
 └─────────────────────────────────────────────┘
       │
       ▼
 Generated Command
       │
       ▼
 Execution Confirmation
```

---

## License

MIT. Use it, fork it, rename it, ignore it.
