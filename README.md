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

Then I thought: there's a `man` command. There's no `woman` command. Not for any real reason. Nobody just... did it. And that felt a little sad.

So I built one over a weekend, mostly for fun, partly out of spite for a naming gap that's sat in Unix since forever.

`woman` skips the manual page entirely. She looks at your current directory, your shell history, and your OS, then prints the exact command you need. You decide whether to run it.

---

## What it does

You type what you want in plain English. `woman` gathers some context first: your OS, the files in your current directory, your last 5 shell commands. Then it asks an LLM for the right command, prints the result, and asks if you want to run it.

That's the whole thing.

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

```bash
pip install openai        # OpenAI (default)
pip install anthropic     # Anthropic / Claude
pip install requests      # Ollama (local models)
```

### 3. Set your API key

In your `~/.bashrc` or `~/.zshrc`:

```bash
export OPENAI_API_KEY="sk-..."
# or
export ANTHROPIC_API_KEY="sk-ant-..."
# Ollama needs no key, just a running server
```

### 4. Add the alias

```bash
alias woman='python3 ~/.local/bin/woman.py'
```

### 5. Reload your shell

```bash
source ~/.bashrc   # or: source ~/.zshrc
```

---

## Configuration

`woman` picks up your provider from whichever API key is set. You can override it:

| Variable | What it does | Default |
|---|---|---|
| `WOMAN_PROVIDER` | `openai`, `anthropic`, or `ollama` | Auto-detected |
| `WOMAN_MODEL` | Override the model name | Provider default |
| `OPENAI_API_KEY` | Your OpenAI key | — |
| `ANTHROPIC_API_KEY` | Your Anthropic key | — |
| `OLLAMA_HOST` | Your Ollama server URL | `http://localhost:11434` |

```bash
# Anthropic
export WOMAN_PROVIDER=anthropic
export WOMAN_MODEL=claude-sonnet-4-20250514

# A specific OpenAI model
export WOMAN_PROVIDER=openai
export WOMAN_MODEL=gpt-4-turbo

# Local Ollama
export WOMAN_PROVIDER=ollama
export WOMAN_MODEL=llama3
```

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
 ┌─────────────────────────┐
 │ OS + distro             │
 │ Current directory path  │
 │ Files in directory      │
 │ Last 5 shell commands   │
 └─────────────────────────┘
       │
       ▼
 LLM Call (OpenAI / Anthropic / Ollama)
 ┌─────────────────────────────────────────────┐
 │ System: "Return ONLY the raw command.       │
 │          No markdown. No explanation.       │
 │          No yapping."                       │
 │ User:   query + all gathered context        │
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

No LLM configured? It falls back to a local tldr cache, then cheat.sh. Adding a new provider is about 10 lines of Python in the `PROVIDERS` dict.

---

## Disclaimer

This tool was written entirely by an LLM (Claude, specifically). The person who prompted it into existence takes no responsibility for what it suggests or runs.

If you `y` a command and something breaks, that's between you and your terminal. Read what it prints before you confirm it. The prompt is there for a reason.

By using `woman`, you're agreeing that you can read a one-line shell command and make a basic judgment call about it.

---

## Contributing

Open an issue or a PR. All feedback welcome, including "the name is ridiculous."

---

## License

MIT. Free to use, fork, rename, or ignore.

---

<div align="center">

*Built because `man` existed and `woman` didn't.*

`$ woman help me`

</div>
