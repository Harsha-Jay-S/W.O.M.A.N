#!/usr/bin/env python3
"""
woman — Working Omniscient Manager of Actual Needs
The AI-powered counterpart to the Linux `man` command.

Usage:
    woman <natural language query>
    woman extract this gzip file
    woman find all python files modified today
"""

from __future__ import annotations  # enables str | None syntax on Python 3.9

import os
import sys
import platform
import subprocess
import shutil
import urllib.request
import urllib.parse
import urllib.error
import zipfile
import io
import re
import shlex
import argparse
from pathlib import Path

__version__ = "2.0"

# ─── Configuration & Timeouts ─────────────────────────────────────────────────

TIMEOUT_TLDR_DOWNLOAD = 15  # Seconds to wait when downloading the tldr database
TIMEOUT_CHTSH_REQUEST = 5   # Seconds to wait for cheat.sh to respond
TIMEOUT_OLLAMA_API = 60     # Seconds to wait for local Ollama inference

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
    """Queries the OpenAI API to generate a command based on the context."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package not installed. Run: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set.")

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
    """Queries the Anthropic Claude API to generate a command based on the context."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package not installed. Run: pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set.")

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
    """Queries a local Ollama instance to generate a command."""
    try:
        import requests
    except ImportError:
        raise ImportError("requests package not installed. Run: pip install requests")

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
        resp = requests.post(f"{host}/api/chat", json=payload, timeout=TIMEOUT_OLLAMA_API)
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Ollama request failed: {e}")


PROVIDERS = {
    "openai":    call_openai,
    "anthropic": call_anthropic,
    "ollama":    call_ollama,
}


# ─── Non-LLM Fallback Backends ────────────────────────────────────────────────

def inject_context(command: str, context: str, query: str) -> str:
    """
    Takes a generic tldr/cht.sh command and injects actual filenames from the directory.
    Uses basic heuristics to pick the right file based on the query or command type.
    """
    files = []
    lines = context.splitlines()
    in_files = False
    
    for line in lines:
        if line.startswith("Files in current directory:"):
            in_files = True
            continue
        if in_files and line.strip() == "": continue
        if in_files and "Recent shell history" in line: break
        if in_files:
            # `ls -a` in non-interactive mode outputs one entry per line,
            # so treat the whole line as the filename (preserves spaces in names)
            f = line.strip()
            if f and f not in (".", ".."):
                files.append(f)
                    
    if files:
        selected_file = files[0]  # Default to first file
        
        # Heuristic 1: Did the user mention a specific file in their query?
        for f in files:
            if f in query:
                selected_file = f
                break
        else:
            # Heuristic 2: Match file extensions based on the command
            if any(cmd in command for cmd in ["tar", "unzip", "gzip", "gunzip"]):
                archives = [f for f in files if f.endswith(('.tar', '.gz', '.zip', '.tgz', '.bz2'))]
                if archives: selected_file = archives[0]
            elif "python" in command:
                pys = [f for f in files if f.endswith('.py')]
                if pys: selected_file = pys[0]

        # Safely escape the filename to prevent spaces/symbols from breaking the shell
        safe_file = shlex.quote(selected_file)
        command = re.sub(
            r'<(?:file|filename|path|archive|directory|source|target)[^>]*>', 
            safe_file, 
            command, 
            flags=re.IGNORECASE
        )
    return command


def call_tldr(query: str, context: str = "") -> str:
    """
    Queries a local, offline cache of tldr pages.
    Downloads the database on the first run if it doesn't exist.
    """
    cache_dir = Path.home() / ".cache" / "woman" / "tldr"
    if not cache_dir.exists():
        try:
            print(f"{DIM}Downloading local tldr database for the first time...{RESET}".ljust(60), file=sys.stderr, end="\r")
            # Use GitHub releases URL; tldr.sh/assets may return 403
            url = "https://github.com/tldr-pages/tldr/releases/latest/download/tldr.zip"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=TIMEOUT_TLDR_DOWNLOAD) as response:
                data = response.read()
            # Only create the directory after a successful download
            cache_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                z.extractall(cache_dir)
        except (urllib.error.URLError, zipfile.BadZipFile):
            return ""
            
    pages_dir = cache_dir / "pages"
    if not pages_dir.exists(): 
        return ""
    
    os_name = platform.system().lower()
    targets = ["common"]
    if os_name == "linux": targets.append("linux")
    elif os_name == "darwin": targets.append("osx")
    elif os_name == "windows": targets.append("windows")
    
    best_match_cmd = ""
    best_score = 0
    query_words = set(re.findall(r'\w+', query.lower()))
    if not query_words: return ""
    
    for t in targets:
        target_dir = pages_dir / t
        if not target_dir.exists(): continue
        for page in target_dir.glob("*.md"):
            try:
                with open(page, 'r', encoding='utf-8') as f:
                    content = f.read()
                lines = content.splitlines()

                # FIX: tokenize the page title so hyphenated names like "git-log"
                # correctly match query words {"git", "log"} instead of checking
                # if the full string "git-log" is literally in the query word set.
                title_words = set(re.findall(r'\w+', page.stem.lower()))
                title_score = 3 if title_words & query_words else 0
                
                for i, line in enumerate(lines):
                    if line.startswith(">"):
                        desc = line[1:].strip().lower()
                        desc_words = set(re.findall(r'\w+', desc))
                        score = title_score + len(query_words.intersection(desc_words))
                        
                        # Match threshold
                        if score > best_score and score >= max(1, len(query_words)//2):
                            for j in range(i+1, len(lines)):
                                if lines[j].startswith("`"):
                                    best_score = score
                                    best_match_cmd = lines[j].strip("` ")
                                    break
            except OSError:
                continue
                
    if best_match_cmd:
        return inject_context(best_match_cmd, context, query)
        
    return ""


def call_chtsh(query: str, context: str = "") -> str:
    """Queries cheat.sh as a no-key web fallback."""
    slug = urllib.parse.quote_plus(query)
    url = f"https://cht.sh/{slug}?QT"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_CHTSH_REQUEST) as response:
            text = response.read().decode('utf-8')
            lines = text.splitlines()
            # Filter out comments to return just the raw command
            commands = [line for line in lines if line.strip() and not line.strip().startswith('#')]
            if commands:
                return inject_context(commands[0].strip(), context, query)
    except urllib.error.URLError:
        pass
    return ""


# ─── Context Gathering ────────────────────────────────────────────────────────

def gather_context() -> str:
    """Gathers OS details, directory contents, and shell history to feed the AI."""
    lines = []

    uname = platform.uname()
    os_info = f"{uname.system} {uname.release}"
    if uname.system == "Linux":
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        os_info = line.split("=", 1)[1].strip().strip('"')
                        break
        except OSError:
            pass
    lines.append(f"OS: {os_info} ({uname.machine})")

    cwd = Path.cwd()
    lines.append(f"Current directory: {cwd}")

    try:
        result = subprocess.run(["ls", "-a"], capture_output=True, text=True, timeout=5)
        files = result.stdout.strip()
        lines.append(f"Files in current directory:\n{files}")
    except (subprocess.SubprocessError, OSError):
        try:
            entries = [p.name for p in cwd.iterdir()]
            lines.append(f"Files in current directory:\n" + "\n".join(entries))
        except OSError:
            lines.append("Files in current directory: (unavailable)")

    history_lines = _get_shell_history(5)
    if history_lines:
        lines.append("Recent shell history (most recent last):\n" + "\n".join(history_lines))
    else:
        lines.append("Recent shell history: (unavailable)")

    return "\n\n".join(lines)


def _get_shell_history(n: int) -> list[str]:
    """Attempts to read the last 'n' lines from the user's bash or zsh history."""
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
                text = raw.decode("utf-8", errors="replace")
                commands = []
                for line in text.splitlines():
                    line = line.strip()
                    if not line: continue
                    if line.startswith(": ") and ";" in line:
                        line = line.split(";", 1)[1]
                    commands.append(line)
                return commands[-n:] if len(commands) >= n else commands
            except OSError:
                continue
    return []


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _die(msg: str) -> None:
    print(f"{RED}Error: {msg}{RESET}", file=sys.stderr)
    sys.exit(1)

def _print_banner():
    print(f"{DIM}woman — Working Omniscient Manager of Actual Needs{RESET}", file=sys.stderr)

def _resolve_provider(cli_provider: str | None = None, cli_model: str | None = None) -> tuple[str | None, str | None]:
    """
    Determines which LLM backend to use based on configuration.
    Priority: CLI Flags -> Env Vars -> Auto-detect keys.
    Returns (None, None) if the user has no keys, letting the script fallback to tldr/cht.sh.
    """
    provider = (cli_provider or os.environ.get("WOMAN_PROVIDER", "")).lower()
    model    = cli_model or os.environ.get("WOMAN_MODEL", None)

    if provider and provider in PROVIDERS:
        return provider, model

    if os.environ.get("OPENAI_API_KEY"):
        return "openai", model
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", model
    if os.environ.get("OLLAMA_HOST") or shutil.which("ollama"):
        return "ollama", model

    # No LLM configured. Returning None triggers the tldr cascade
    return None, None


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="woman",
        description=f"{BOLD}woman{RESET} — Working Omniscient Manager of Actual Needs\n"
                    f"The AI-powered counterpart to the Linux `man` command.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=f"{CYAN}Examples:{RESET}\n"
               f"  woman extract this gzip file\n"
               f"  woman kill the process using port 8080\n"
               f"  woman -p ollama summarize system logs"
    )
    
    parser.add_argument("query", nargs="*", help="What you want to do in natural language")
    parser.add_argument("-p", "--provider", choices=["openai", "anthropic", "ollama"], help="Force a specific LLM provider")
    parser.add_argument("-m", "--model", help="Force a specific LLM model (e.g., gpt-4o, llama3)")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s v{__version__}")

    args = parser.parse_args()
    
    if not args.query:
        parser.print_help()
        sys.exit(0)
        
    query = " ".join(args.query)

    _print_banner()
    print(f"{DIM}Gathering context...{RESET}", file=sys.stderr, end="\r")

    context = gather_context()
    provider_name, model_override = _resolve_provider(args.provider, args.model)
    
    command = ""

    # CASCADE TIER 1: The LLM (if configured)
    if provider_name:
        print(f"{DIM}Asking {provider_name}...        {RESET}", file=sys.stderr, end="\r")
        caller = PROVIDERS[provider_name]
        kwargs: dict = {"query": query, "context": context}
        if model_override: kwargs["model"] = model_override
        
        try:
            command = caller(**kwargs)
        except KeyboardInterrupt:
            print("\nAborted.", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"{DIM}LLM failed ({e}). Falling back...{RESET}".ljust(60), file=sys.stderr, end="\r")

    # CASCADE TIER 2: Local `tldr` search (Offline, Fast)
    if not command:
        print(f"{DIM}Searching local tldr manuals...{RESET}".ljust(60), file=sys.stderr, end="\r")
        command = call_tldr(query, context)

    # CASCADE TIER 3: `cheat.sh` (No-key API, broad knowledge)
    if not command:
        print(f"{DIM}Searching cheat.sh internet fallback...{RESET}".ljust(60), file=sys.stderr, end="\r")
        command = call_chtsh(query, context)

    if not command:
        print(" " * 60, file=sys.stderr, end="\r")
        _die("All backends failed to find a matching command. Try rephrasing your query or setting an API key.")

    # Clear the status line
    print(" " * 60, file=sys.stderr, end="\r")

    # Sanitize markdown artifacts safely
    # Must check for fenced blocks BEFORE stripping backtick chars,
    # otherwise ```bash becomes "bash\n..." after strip("`")
    command = command.strip()
    if command.startswith("```"):
        command = "\n".join(command.splitlines()[1:])  # drop ```[lang] line
    if command.endswith("```"):
        command = "\n".join(command.splitlines()[:-1])  # drop closing ```
    command = command.strip().strip("`").strip()

    # Print
    print(f"\n  {CYAN}{BOLD}{command}{RESET}\n")

    # Prompt
    try:
        answer = input(f"{YELLOW}Execute this command? (y/n): {RESET}").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print(f"\n{DIM}Aborted.{RESET}")
        sys.exit(0)

    if answer in ("y", "yes"):
        print()
        try:
            shell = os.environ.get("SHELL", "/bin/sh")
            result = subprocess.run([shell, "-c", command], text=True)
            if result.returncode != 0:
                print(f"\n{RED}Command exited with code {result.returncode}.{RESET}", file=sys.stderr)
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
