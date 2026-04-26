#!/usr/bin/env python3
"""
woman — Working Omniscient Manager of Actual Needs
The intuitive, AI-powered counterpart to the Linux `man` command.

Usage:
    woman <natural language query>
    woman extract this gzip file
    woman find all python files modified today
    woman kill the process using port 8080

Setup:
    pip install openai          # default provider
    pip install anthropic       # optional: Anthropic backend
    export OPENAI_API_KEY=...   # or ANTHROPIC_API_KEY / OLLAMA_HOST
    alias woman='python3 /path/to/woman.py'
"""

import os
import sys
import platform
import subprocess
import shutil
from pathlib import Path


# ─── ANSI Colors ──────────────────────────────────────────────────────────────

CYAN    = "\033[96m"
YELLOW  = "\033[93m"
GREEN   = "\033[92m"
RED     = "\033[91m"
DIM     = "\033[2m"
BOLD    = "\033[1m"
RESET   = "\033[0m"


# ─── LLM Backend Abstraction ──────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a CLI assistant. The user will describe what they want to do in natural language. "
    "You will be given their OS, current working directory, directory contents, and recent shell history as context. "
    "Your job is to return the single, exact terminal command that accomplishes their goal. "
    "RULES: "
    "1. Return ONLY the raw command. No markdown, no backticks, no code fences. "
    "2. No explanations, no preamble, no yapping. "
    "3. If multiple commands are needed, chain them with && or ; on a single line. "
    "4. Tailor the command to the user's specific OS and files where relevant."
)


def call_openai(query: str, context: str, model: str = "gpt-4o") -> str:
    try:
        from openai import OpenAI
    except ImportError:
        _die("openai package not installed. Run: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        _die("OPENAI_API_KEY environment variable not set.")

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"{context}\n\nUser query: {query}"},
        ],
        temperature=0,
        max_tokens=256,
    )
    return response.choices[0].message.content.strip()


def call_anthropic(query: str, context: str, model: str = "claude-sonnet-4-20250514") -> str:
    try:
        import anthropic
    except ImportError:
        _die("anthropic package not installed. Run: pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        _die("ANTHROPIC_API_KEY environment variable not set.")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f"{context}\n\nUser query: {query}"},
        ],
    )
    return message.content[0].text.strip()


def call_ollama(query: str, context: str, model: str = "llama3") -> str:
    try:
        import requests
    except ImportError:
        _die("requests package not installed. Run: pip install requests")

    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"{context}\n\nUser query: {query}"},
        ],
        "stream": False,
        "options": {"temperature": 0},
    }
    try:
        resp = requests.post(f"{host}/api/chat", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()
    except Exception as e:
        _die(f"Ollama request failed: {e}")


PROVIDERS = {
    "openai":    call_openai,
    "anthropic": call_anthropic,
    "ollama":    call_ollama,
}


# ─── Context Gathering ────────────────────────────────────────────────────────

def gather_context() -> str:
    lines = []

    # OS / distro
    uname = platform.uname()
    os_info = f"{uname.system} {uname.release}"
    if uname.system == "Linux":
        # Try to get distro name from /etc/os-release
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        os_info = line.split("=", 1)[1].strip().strip('"')
                        break
        except OSError:
            pass
    lines.append(f"OS: {os_info} ({uname.machine})")

    # Current working directory
    cwd = Path.cwd()
    lines.append(f"Current directory: {cwd}")

    # Directory listing
    try:
        result = subprocess.run(
            ["ls", "-a"], capture_output=True, text=True, timeout=5
        )
        files = result.stdout.strip()
        lines.append(f"Files in current directory:\n{files}")
    except Exception:
        try:
            entries = [p.name for p in cwd.iterdir()]
            lines.append(f"Files in current directory:\n" + "\n".join(entries))
        except Exception:
            lines.append("Files in current directory: (unavailable)")

    # Recent shell history (last 5 commands)
    history_lines = _get_shell_history(5)
    if history_lines:
        lines.append("Recent shell history (most recent last):\n" + "\n".join(history_lines))
    else:
        lines.append("Recent shell history: (unavailable)")

    return "\n\n".join(lines)


def _get_shell_history(n: int) -> list[str]:
    """Try to read the last n commands from bash or zsh history."""
    # Prefer the file pointed to by $HISTFILE, then fall back to defaults
    candidates = []

    histfile = os.environ.get("HISTFILE")
    if histfile:
        candidates.append(Path(histfile).expanduser())

    candidates += [
        Path.home() / ".bash_history",
        Path.home() / ".zsh_history",
        Path.home() / ".history",
    ]

    for path in candidates:
        if path.exists():
            try:
                raw = path.read_bytes()
                # zsh extended history lines start with ": <timestamp>:<elapsed>;"
                text = raw.decode("utf-8", errors="replace")
                commands = []
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    # Strip zsh extended history prefix
                    if line.startswith(": ") and ";" in line:
                        line = line.split(";", 1)[1]
                    commands.append(line)
                return commands[-n:] if len(commands) >= n else commands
            except Exception:
                continue

    return []


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _die(msg: str) -> None:
    print(f"{RED}Error: {msg}{RESET}", file=sys.stderr)
    sys.exit(1)


def _print_banner():
    print(
        f"{DIM}woman — Working Omniscient Manager of Actual Needs{RESET}",
        file=sys.stderr,
    )


def _resolve_provider() -> tuple[str, str | None]:
    """
    Determine which LLM backend to use.
    Priority: WOMAN_PROVIDER env var → auto-detect from available API keys.
    Returns (provider_name, optional_model_override).
    """
    provider = os.environ.get("WOMAN_PROVIDER", "").lower()
    model    = os.environ.get("WOMAN_MODEL", None)

    if provider and provider in PROVIDERS:
        return provider, model

    # Auto-detect
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", model
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", model
    if os.environ.get("OLLAMA_HOST") or shutil.which("ollama"):
        return "ollama", model

    _die(
        "No LLM provider configured.\n"
        "  Set one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, or OLLAMA_HOST\n"
        "  Or set WOMAN_PROVIDER=openai|anthropic|ollama explicitly."
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(
            f"{BOLD}woman{RESET} — Working Omniscient Manager of Actual Needs\n\n"
            f"  {CYAN}Usage:{RESET}  woman <natural language query>\n\n"
            f"  {CYAN}Examples:{RESET}\n"
            f"    woman extract this gzip file\n"
            f"    woman find all python files modified today\n"
            f"    woman kill the process using port 8080\n"
            f"    woman show disk usage sorted by size\n\n"
            f"  {CYAN}Config (env vars):{RESET}\n"
            f"    WOMAN_PROVIDER   openai | anthropic | ollama  (default: auto-detect)\n"
            f"    WOMAN_MODEL      override the model name\n"
            f"    OPENAI_API_KEY   required for OpenAI backend\n"
            f"    ANTHROPIC_API_KEY  required for Anthropic backend\n"
            f"    OLLAMA_HOST      Ollama server URL (default: http://localhost:11434)\n"
        )
        sys.exit(0)

    query = " ".join(sys.argv[1:])

    _print_banner()
    print(f"{DIM}Gathering context...{RESET}", file=sys.stderr, end="\r")

    context = gather_context()
    provider_name, model_override = _resolve_provider()
    caller = PROVIDERS[provider_name]

    print(f"{DIM}Asking {provider_name}...        {RESET}", file=sys.stderr, end="\r")

    # Build kwargs — only pass model if explicitly overridden
    kwargs = {"query": query, "context": context}
    if model_override:
        kwargs["model"] = model_override

    try:
        command = caller(**kwargs)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        _die(str(e))

    # Clear the status line
    print(" " * 60, file=sys.stderr, end="\r")

    # Sanitize: strip accidental backticks or markdown fences the model might sneak in
    command = command.strip().strip("`")
    if command.startswith("```"):
        command = "\n".join(command.splitlines()[1:])
    if command.endswith("```"):
        command = "\n".join(command.splitlines()[:-1])
    command = command.strip()

    # Print the suggested command
    print(f"\n  {CYAN}{BOLD}{command}{RESET}\n")

    # Prompt for execution
    try:
        answer = input(f"{YELLOW}Execute this command? (y/n): {RESET}").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print(f"\n{DIM}Aborted.{RESET}")
        sys.exit(0)

    if answer == "y":
        print()
        try:
            # Use the user's shell so aliases, PATH, etc. all work correctly
            shell = os.environ.get("SHELL", "/bin/sh")
            result = subprocess.run(
                [shell, "-c", command],
                text=True,
            )
            if result.returncode != 0:
                print(
                    f"\n{RED}Command exited with code {result.returncode}.{RESET}",
                    file=sys.stderr,
                )
                sys.exit(result.returncode)
        except KeyboardInterrupt:
            print(f"\n{DIM}Interrupted.{RESET}")
            sys.exit(130)
        except Exception as e:
            _die(f"Execution failed: {e}")
    else:
        print(f"{DIM}Command not executed. Goodbye!{RESET}")


if __name__ == "__main__":
    main()
