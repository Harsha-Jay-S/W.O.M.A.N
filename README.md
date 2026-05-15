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
- **Self-installing UI.** Uses `rich` and `questionary` for a purple terminal interface. If they're missing, it asks to install them.
- **Reads your `$PATH`.** It knows what tools you actually have.
- **Parses man pages on the fly.** If a tool isn't indexed, it pulls the first 300 lines of the man page and works from there — heuristics or AI, depending on your config.
- **Works offline.** No LLM provider set up? It falls back to local heuristic matching.

---

## Installation

### 1. Install via `uv` or `pip`

```bash
uv pip install -e .[ui]
# OR: python3 -m pip install -e .[ui]
# OR: bash install.sh
```

### 2. Add the alias

```bash
alias woman='python3 -m woman_revamp'
```

### 3. Run setup

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
 "Execute this command? (y/n)"
       │
      y/n
       │
       ▼
 subprocess → your shell → output
```

---

## Disclaimer

Written entirely by an LLM. I (the human who prompted it into existence) take no responsibility for what it suggests or runs.

If you `y` a command and something breaks, that's on you. The confirmation prompt is there so you actually read the command first. Use it.

---

## License

MIT. Use it, fork it, rename it, ignore it.

---

<div align="center">

*Built because `man` existed and `woman` didn't.*

</div>
