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

It was late. I forgot a `tar` flag. Again. I typed `man tar`, got my answer, and moved on.

Then I thought: there's a `man` command. There's no `woman` command. Not for any real reason. Nobody just... did it.

So I built one over a weekend, mostly for fun, partly out of spite for a naming gap that's sat in Unix since forever.

`woman` skips the manual page entirely. She looks at your current directory, your shell history, and your OS, then prints the exact command you need. You decide whether to run it.

---

## What it does

You type what you want in plain English. `woman` gathers context first — your OS, the files in your current directory, your last 5 shell commands — then works through three backends in order until it finds an answer:

1. **LLM** — if a provider is configured, this runs first. It gets the full context and returns a command tailored to your exact setup. OpenAI, Anthropic, Groq, Mistral, OpenRouter, Together, Perplexity, Fireworks, LM Studio, Ollama, or anything that speaks the OpenAI wire format.
2. **Local tldr cache** — if no LLM is configured, or if the LLM fails, it searches a local offline copy of [tldr-pages](https://tldr.sh). Fast, no network needed after the first run.
3. **cheat.sh** — last resort. Hits the cheat.sh API, which needs no key and covers a broad range of commands.

You don't need an API key. The LLM just gives better, more context-aware answers.

---

## Demo

```
$ woman find all files larger than 100MB

  find . -type f -size +100M

Execute this command? (y/n): y

./node_modules/.cache/webpack/something-cursed.pack
./videos/raw-footage-final-FINAL-v3.mp4
```

---

## Installation

### 1. Download the script

```bash
mkdir -p ~/.local/bin
curl -o ~/.local/bin/woman.py https://your-repo-url/woman.py
chmod +x ~/.local/bin/woman.py
```

### 2. Install dependencies

The LLM backends are optional. Install only what you need:

```bash
pip install openai        # OpenAI, Groq, Mistral, OpenRouter, or any OpenAI-compat provider
pip install anthropic     # Anthropic / Claude
# Ollama needs no package — just a running local server
```

No key? Skip this entirely. `woman` falls back to tldr and cheat.sh automatically which may not be as reliable as the AI so check twice before running those commands.

### 3. Add the alias

```bash
alias woman='python3 ~/.local/bin/woman.py'
```

### 4. Reload your shell

```bash
source ~/.bashrc   # or: source ~/.zshrc
```

### 5. Set up a provider (optional but recommended)

```bash
woman config
```

Pick a provider, paste your key, choose a model. You can browse live models from the API if you're not sure which one to use. The result lands in `~/.config/woman/config.toml` and you don't have to think about it again.

---

## Configuration

### Config file

`woman config` writes `~/.config/woman/config.toml` for you. If you want to edit it by hand, it looks like this:

```toml
[defaults]
provider = "groq"

[provider.groq]
protocol = "openai"
base_url = "https://api.groq.com/openai/v1"
api_key  = "gsk_..."
model    = "llama-3.3-70b-versatile"

[provider.local]
protocol = "ollama"
base_url = "http://localhost:11434"
model    = "llama3.2"
```

Multiple providers, one default. `-p` to pick a different one for a single query.

```bash
woman config --list           # see everything configured
woman models                  # list models for your default provider
woman models --provider groq  # list models for a specific one
woman -p groq "your query"    # use a specific provider once
woman -m llama3.2 "..."       # override the model for one query
```

### Supported providers

| Provider | Protocol | Notes |
|---|---|---|
| `openai` | openai | GPT-4o, o1, etc. |
| `anthropic` | anthropic | Claude models |
| `groq` | openai | Fast inference, free tier |
| `openrouter` | openai | Routes to many models |
| `together` | openai | Open-source models |
| `mistral` | openai | Mistral's own API |
| `fireworks` | openai | Fast open-source inference |
| `perplexity` | openai | Web search built in |
| `ollama` | ollama | Local models, no key needed |
| `lmstudio` | openai | Local server, no key needed |
| `custom` | openai | Any OpenAI-compatible endpoint |

Not listed? Pick `custom` in the wizard, supply a base URL, done.

### Environment variables

Still supported. Good for CI or one-offs where you don't want a config file:

| Variable | What it does |
|---|---|
| `OPENAI_API_KEY` | Picked up automatically |
| `ANTHROPIC_API_KEY` | Same |
| `OLLAMA_HOST` | Ollama server URL (default: `http://localhost:11434`) |
| `WOMAN_PROVIDER` | Name of a configured provider |
| `WOMAN_MODEL` | Model override for this session |
| `WOMAN_API_KEY` | Generic key — pair with `WOMAN_PROTOCOL` and `WOMAN_BASE_URL` for any provider without a config entry |
| `WOMAN_PROTOCOL` | `openai`, `anthropic`, or `ollama` |
| `WOMAN_BASE_URL` | Endpoint base URL |

---

## More examples

```bash
# Compression
woman extract this tar.gz file
woman zip all the jpg files in this folder

# Processes
woman find what's running on port 8080
woman kill the process using the most memory

# Files
woman find all logs older than 7 days and delete them
woman rename all .jpeg files to .jpg

# Network
woman check if google.com is reachable
woman show my public IP address

# Git
woman undo my last commit but keep the changes
woman show me all branches that have been merged
```

---

## How it works

```
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
 Tier 1 — LLM (if configured)
 ┌─────────────────────────────────────────────┐
 │ Any provider in ~/.config/woman/config.toml │
 │ OpenAI · Anthropic · Groq · Mistral         │
 │ OpenRouter · Together · Ollama · custom...  │
 │                                             │
 │ System: "Return ONLY the raw command.       │
 │          No markdown. No explanation.       │
 │          No yapping."                       │
 │ User:   query + all gathered context        │
 └─────────────────────────────────────────────┘
       │ no provider configured, or call fails
       ▼
 Tier 2 — Local tldr cache (offline, fast)
 ┌─────────────────────────────────────────────┐
 │ Downloaded once to ~/.cache/woman/tldr      │
 │ Searches tldr-pages for a matching command  │
 │ Injects real filenames from your directory  │
 └─────────────────────────────────────────────┘
       │ no match found
       ▼
 Tier 3 — cheat.sh (web fallback, no key)
 ┌─────────────────────────────────────────────┐
 │ Hits cht.sh API                             │
 │ Broad coverage, works without any account   │
 └─────────────────────────────────────────────┘
       │
       ▼
 Print command in cyan
       │
       ▼
 "Execute this command? (y/n)"
       │
      y/n
       │
       ▼
 subprocess → your shell → output
```

Adding a provider is `woman config`. No Python required.

---

## Disclaimer

This tool was written entirely by an LLM (Claude, specifically). The person who prompted it into existence takes no responsibility for what it suggests or runs.

If you `y` a command and something breaks, that's between you and your terminal. Read what it prints before you confirm it. The prompt is there for a reason.

By using `woman`, you're agreeing that you can read a one-line shell command and make a basic judgment call about it.

---

## Contributing

Open an issue or a PR. All feedback welcome.

---

## License

MIT. Free to use, fork, rename, or ignore.

---

<div align="center">

*Built because `man` existed and `woman` didn't.*

`$ woman help me`

</div>
