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

It was late. I forgot a `nmap` flag. Again. I typed `man nmap`, got my answer, and moved on.

Then I thought: there's a `man` command. There's no `woman` command. Not for any real reason. Nobody just... did it.

So I built one over a weekend, mostly for fun, partly out of spite for a naming gap that's sat in Unix since forever.

`woman` skips the manual page entirely. She looks at your current directory, your shell history, and your OS, then prints the exact command you need in a sleek purple UI. You decide whether to run it.

---

## What it does (The Revamp)

You type what you want in plain English. `woman` gathers context first — your OS, the files in your current directory, and your last 5 shell commands — and builds a command tailored to your exact setup using a completely revamped engine.

### Core Features:
- **Zero-Dependency Core:** The engine uses native Python `urllib` to talk to LLMs. No heavy SDKs, ensuring millisecond boot times.
- **Auto-Healing UI:** Uses `rich` and `questionary` for a premium purple-gradient terminal experience. If they aren't installed, `woman` will automatically prompt to bootstrap and install them for you.
- **Dynamic `$PATH` Scanner:** Automatically detects the tools installed on your machine.
- **Just-In-Time (JIT) Man-Page Parsing:** If a tool's syntax isn't known, it extracts the first 300 lines of its `man` page on the fly and intelligently parses it using either heuristics or AI.
- **Local Fallback Engine:** Works entirely offline using exact-match heuristics if no AI provider is configured or available.

You don't *need* an API key to use the offline heuristic engine or a local Ollama instance, but configuring an LLM gives the most context-aware answers.

---

## Installation

### 1. Install via `uv` (Recommended) or `pip`

Clone the repo and install the UI dependencies automatically:

```bash
uv pip install -e .[ui]
# OR: python3 -m pip install -e .[ui]
# OR simply run: bash install.sh
```

### 2. Add the alias

```bash
alias woman='python3 -m woman_revamp'
```

### 3. Run the Setup Wizard

The first time you run `woman`, it launches an interactive wizard.

```bash
woman config
```
You can choose:
* **UI Mode:** Rich (purple gradients) or Basic.
* **AI Provider:** Ollama (Local), OpenAI, Anthropic, Gemini, or None (Heuristics only).
* **Indexing Mode:** JIT (Just-in-Time, recommended) or Batch.

Settings are saved in `~/.config/woman/config.json`.

---

## Configuration & Usage

`woman` automatically tracks your `$PATH`. If you install a new package manager or tool, she will prompt you to refresh her local cache.

```bash
woman --list                                  # List all indexed tools
woman --refresh-index                         # Force refresh the PATH cache
woman --index-tool docker                     # Manually index a specific tool
woman "undo my last git commit"               # Normal usage
woman --json "what is using port 8080"        # Output raw scoring JSON
```

### Supported AI Providers
- **`ollama`**: Local models (default endpoint `http://localhost:11434`). Fast, private, no keys.
- **`openai`**: GPT-4o, etc.
- **`anthropic`**: Claude 3.5, etc.
- **`gemini`**: Google Gemini API.
- **`none`**: Pure offline local heuristics matching.

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
 │ Passes context + man snippet to LLM via     │
 │ zero-dependency urllib HTTP client.         │
 └─────────────────────────────────────────────┘
       │
       ▼
 Print command in Rich Purple UI
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

This tool was written entirely by an LLM. The person who prompted it into existence takes no responsibility for what it suggests or runs.

If you `y` a command and something breaks, that's between you and your terminal. Read what it prints before you confirm it. The prompt is there for a reason.

By using `woman`, you're agreeing that you can read a one-line shell command and make a basic judgment call about it.

---

## License

MIT. Free to use, fork, rename, or ignore.

---

<div align="center">

*Built because `man` existed and `woman` didn't.*

`$ woman help me`

</div>