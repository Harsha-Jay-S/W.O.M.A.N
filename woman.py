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
import json
import getpass
import argparse
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib          # Python 3.11+
except ImportError:
    tomllib = None          # handled by _load_toml fallback below

__version__ = "3.0"

CONFIG_PATH = Path.home() / ".config" / "woman" / "config.toml"

# ─── Provider Config Dataclass ────────────────────────────────────────────────

@dataclass
class ProviderConfig:
    """Represents one configured LLM backend."""
    name:     str
    protocol: str           # "openai" | "anthropic" | "ollama"
    model:    str
    api_key:  str | None = None
    base_url: str | None = None

    def display(self) -> str:
        key_hint = f"sk-...{self.api_key[-4:]}" if self.api_key else "(no key)"
        url_hint = self.base_url or "(default)"
        return (f"  {BOLD}{self.name}{RESET}  protocol={self.protocol}  "
                f"model={self.model}  key={key_hint}  url={url_hint}")

# ─── Configuration & Timeouts ─────────────────────────────────────────────────

TIMEOUT_TLDR_DOWNLOAD = 15  # Seconds to wait when downloading the tldr database
TIMEOUT_CHTSH_REQUEST = 5   # Seconds to wait for cheat.sh to respond
TIMEOUT_OLLAMA_API = 180    # Seconds to wait for local Ollama — cold model loads can be slow

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


def _call_openai_compat(query: str, context: str, cfg: ProviderConfig) -> str:
    """
    Calls any OpenAI-compatible endpoint (OpenAI, Groq, Together, Mistral,
    OpenRouter, Fireworks, LM Studio, etc.) using the openai SDK.
    Falls back to a raw urllib request when the SDK is not installed.
    """
    base_url = cfg.base_url or "https://api.openai.com/v1"
    api_key  = cfg.api_key or ""
    model    = cfg.model or "gpt-4o"

    # ── Try SDK first ──────────────────────────────────────────────────────────
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
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
    except ImportError:
        pass  # fall through to raw urllib

    # ── Raw urllib fallback (no extra packages needed) ─────────────────────────
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"{context}\n\nUser query: {query}"},
        ],
        "temperature": 0,
        "max_tokens": 256,
    }).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"].strip()


def _call_anthropic_compat(query: str, context: str, cfg: ProviderConfig) -> str:
    """Calls the Anthropic Messages API."""
    api_key = cfg.api_key or ""
    model   = cfg.model or "claude-sonnet-4-6"

    # ── Try SDK first ──────────────────────────────────────────────────────────
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"{context}\n\nUser query: {query}"}],
        )
        return message.content[0].text.strip()
    except ImportError:
        pass  # fall through to raw urllib

    # ── Raw urllib fallback ────────────────────────────────────────────────────
    payload = json.dumps({
        "model": model,
        "max_tokens": 256,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": f"{context}\n\nUser query: {query}"}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"].strip()


def _call_ollama_compat(query: str, context: str, cfg: ProviderConfig) -> str:
    """
    Queries a local Ollama instance with streaming enabled.
    Thinking tokens (if the model produces them) are shown live to the user
    in dim text; only the final answer is returned as the command.
    """
    host  = (cfg.base_url or "http://localhost:11434").rstrip("/")
    model = cfg.model or "llama3.2"

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"{context}\n\nUser query: {query}"},
        ],
        "stream": True,
        "options": {"temperature": 0},
    }).encode()

    req = urllib.request.Request(
        f"{host}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    THINK_START = re.compile(r'(Thinking\.\.\.|<think>)', re.IGNORECASE)
    THINK_END   = re.compile(r'(\.\.\.done thinking\.|</think>)', re.IGNORECASE)

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_OLLAMA_API) as resp:
            full_response = ""
            in_thinking   = False
            think_buffer  = ""
            answer_buffer = ""

            print(" " * 60, file=sys.stderr, end="\r")

            for raw_line in resp:
                line = raw_line.decode().strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                token = chunk.get("message", {}).get("content", "")
                full_response += token
                done = chunk.get("done", False)

                if THINK_START.search(token):
                    in_thinking = True
                    print(f"\n{DIM}── thinking ──────────────────────────{RESET}", file=sys.stderr)

                if in_thinking:
                    think_buffer += token
                    print(f"{DIM}{token}{RESET}", end="", flush=True, file=sys.stderr)
                    if THINK_END.search(token):
                        in_thinking = False
                        print(f"\n{DIM}── done thinking ─────────────────────{RESET}\n", file=sys.stderr)
                        think_buffer = ""
                else:
                    answer_buffer += token

                if done:
                    break

            final = answer_buffer.strip() if answer_buffer.strip() else full_response.strip()
            return final

    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        if "model" in body.lower() and ("not found" in body.lower() or "pull" in body.lower()):
            raise RuntimeError(
                f"Model '{model}' not found in Ollama. Run: ollama pull {model}\n"
                f"Your installed models: run 'ollama list' to check."
            )
        raise RuntimeError(f"Ollama HTTP {e.code}: {body[:200]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Ollama at {host} — is it running? ({e.reason})")
    except (KeyError, ValueError) as e:
        raise RuntimeError(f"Unexpected Ollama response format: {e}")


def _dispatch_provider(query: str, context: str, cfg: ProviderConfig) -> str:
    """Routes a query to the correct protocol implementation."""
    match cfg.protocol:
        case "openai":
            return _call_openai_compat(query, context, cfg)
        case "anthropic":
            return _call_anthropic_compat(query, context, cfg)
        case "ollama":
            return _call_ollama_compat(query, context, cfg)
        case _:
            raise ValueError(f"Unknown protocol '{cfg.protocol}' for provider '{cfg.name}'."
                             f" Valid protocols: openai, anthropic, ollama")



def _extract_command(response: str, os_info: dict | None = None) -> str:
    """
    Extracts just the shell command from an LLM response that may contain
    explanatory text, markdown code blocks, or preamble.

    Strategy (in order):
    1. Pull the first fenced code block  (```...```)
    2. Pull the first inline backtick span (`cmd`)
    3. Scan lines for the first one that looks like a real shell command
    4. Fall back to the first non-empty line
    """
    if os_info is None:
        os_info = _detect_os()
    text = response.strip()

    # 1. Fenced code block — grab the first command inside it
    fenced = re.search(r'```(?:\w+)?\n?(.*?)```', text, re.DOTALL)
    if fenced:
        inner = fenced.group(1).strip()
        # Take only the first line of the block (ignore multi-line examples)
        return inner.splitlines()[0].strip()

    # 2. Inline backtick — e.g. "You can use `rm pseudocode.txt` to delete it"
    inline = re.search(r'`([^`\n]+)`', text)
    if inline:
        return inline.group(1).strip()

    # 3. Line-by-line scan: look for a line that starts with a known command token
    #    or looks like a shell invocation (no sentence-ending punctuation, no "To ", etc.)
    # Dynamically extend SHELL_STARTERS with OS-specific package managers / shells.
    base_cmds = (
        'rm|mv|cp|ls|find|grep|kill|pkill|ps|cat|echo|touch|mkdir|chmod|chown|'
        'tar|zip|unzip|gzip|gunzip|curl|wget|ssh|scp|git|python|python3|pip|pip3|'
        'sudo|systemctl|journalctl|df|du|top|htop|lsof|netstat|ss|ip|ping|'
        'sed|awk|sort|uniq|wc|head|tail|cut|tr|xargs|tee|env|export|source|'
        'cd|pwd|which|type|man|tldr|apt|dnf|yum|pacman|brew|npm|yarn|cargo|make|'
        'go|node|ruby|perl|php|java|gcc|g\\+\\+|docker|podman|kubectl|helm|vim|nano|emacs|'
        'firewall-cmd|semanage|setenforce|restorecon|chcon|'
        'useradd|usermod|groupadd|groupmod|passwd|chpasswd|su|visudo|chroot|'
        'mkfs|fsck|tune2fs|badblocks|blkid|fdisk|parted|mkswap|swapon|swapoff|dd|shred|wipe|'
        'watch|time|timeout|sleep|yes|seq|shuf|bc|expr|test|true|false|base64|md5sum|sha1sum|sha256sum|sha512sum|'
        'gpg|openssl|certbot|cmp|md5|cksum|xdg-open|xclip|xsel'
    )
    os_extra: list[str] = []
    if os_info:
        sys_name = os_info.get("system", "").lower()
        if sys_name == "windows":
            os_extra += ['powershell', 'pwsh', 'cmd', 'winget', 'choco', 'scoop',
                         'msiexec', 'reg', 'netsh', 'ipconfig', 'tasklist', 'taskkill',
                         'sfc', 'dism', 'bcdedit', 'wsl']
        elif sys_name == "darwin":
            os_extra += ['brew', 'open', 'pbcopy', 'pbpaste', 'launchctl',
                         'defaults', 'softwareupdate', 'diskutil', 'hdiutil', 'ditto']
    extra_pattern = ('|' + '|'.join(re.escape(c) for c in os_extra)) if os_extra else ''
    SHELL_STARTERS = re.compile(r'^(' + base_cmds + extra_pattern + r')\b')
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip lines that are clearly prose
        if line.endswith('.') or line.endswith(':') or line.startswith('#'):
            continue
        if re.match(r'^(To |The |This |You |It |Note |Here |Please |Use )', line, re.IGNORECASE):
            continue
        if SHELL_STARTERS.match(line):
            return line

    # 4. Last resort: first non-empty line (same as before, but now only after all else fails)
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line

    return text



# ─── Config File System ───────────────────────────────────────────────────────

# Known well-tested OpenAI-compatible providers for the setup wizard
KNOWN_PROVIDERS: dict[str, dict] = {
    "openai":      {"protocol": "openai",    "base_url": "https://api.openai.com/v1",           "default_model": "gpt-4o"},
    "anthropic":   {"protocol": "anthropic", "base_url": None,                                   "default_model": "claude-sonnet-4-6"},
    "groq":        {"protocol": "openai",    "base_url": "https://api.groq.com/openai/v1",       "default_model": "llama-3.3-70b-versatile"},
    "openrouter":  {"protocol": "openai",    "base_url": "https://openrouter.ai/api/v1",         "default_model": "mistralai/mistral-7b-instruct"},
    "together":    {"protocol": "openai",    "base_url": "https://api.together.xyz/v1",          "default_model": "meta-llama/Llama-3-8b-chat-hf"},
    "mistral":     {"protocol": "openai",    "base_url": "https://api.mistral.ai/v1",            "default_model": "mistral-small-latest"},
    "fireworks":   {"protocol": "openai",    "base_url": "https://api.fireworks.ai/inference/v1","default_model": "accounts/fireworks/models/llama-v3p1-8b-instruct"},
    "perplexity":  {"protocol": "openai",    "base_url": "https://api.perplexity.ai",            "default_model": "llama-3.1-sonar-small-128k-online"},
    "ollama":      {"protocol": "ollama",    "base_url": "http://localhost:11434",               "default_model": "llama3.2"},
    "lmstudio":    {"protocol": "openai",    "base_url": "http://localhost:1234/v1",             "default_model": "local-model"},
    "custom":      {"protocol": "openai",    "base_url": None,                                   "default_model": ""},
}


def _load_toml(path: Path) -> dict:
    """
    Minimal TOML loader for the subset we need:
      [section.subsection] headers and key = "value" / key = number lines.
    Uses stdlib tomllib when available (Python 3.11+), otherwise falls back
    to a small hand-rolled parser that covers our config format.
    """
    if not path.exists():
        return {}

    if tomllib is not None:
        with open(path, "rb") as f:
            return tomllib.load(f)

    # ── Hand-rolled fallback for Python 3.9 / 3.10 ────────────────────────────
    result: dict = {}
    current: dict = result
    current_path: list[str] = []

    def _set_nested(root: dict, keys: list[str], value: dict) -> dict:
        """Navigate/create nested dicts and return the deepest one."""
        node = root
        for k in keys:
            node = node.setdefault(k, {})
        return node

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # Section header: [a.b.c]
            m = re.fullmatch(r'\[([^\]]+)\]', line)
            if m:
                parts = [p.strip() for p in m.group(1).split(".")]
                current_path = parts
                current = _set_nested(result, parts, {})
                continue
            # Key-value: key = "value"  or  key = 123
            m = re.fullmatch(r'(\w+)\s*=\s*(.*)', line)
            if m:
                key = m.group(1)
                raw_val = m.group(2).strip()
                if raw_val.startswith('"') and raw_val.endswith('"'):
                    current[key] = raw_val[1:-1]
                elif raw_val.lower() in ("true", "false"):
                    current[key] = raw_val.lower() == "true"
                else:
                    try:
                        current[key] = int(raw_val)
                    except ValueError:
                        try:
                            current[key] = float(raw_val)
                        except ValueError:
                            current[key] = raw_val
    return result


def _save_toml(path: Path, data: dict) -> None:
    """Writes our config dict back to TOML (supports one level of nesting)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def _quote(v: object) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        return f'"{v}"'

    # Write [defaults] first
    if "defaults" in data:
        lines.append("[defaults]")
        for k, v in data["defaults"].items():
            if not isinstance(v, dict):
                lines.append(f"{k} = {_quote(v)}")
        lines.append("")

    # Write [settings] if present
    if "settings" in data:
        lines.append("[settings]")
        for k, v in data["settings"].items():
            if not isinstance(v, dict):
                lines.append(f"{k} = {_quote(v)}")
        lines.append("")

    # Write [provider.<name>] sections
    providers = data.get("provider", {})
    for name, cfg in providers.items():
        lines.append(f"[provider.{name}]")
        for k, v in cfg.items():
            lines.append(f"{k} = {_quote(v)}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def load_config() -> dict:
    """
    Loads ~/.config/woman/config.toml and returns it as a dict.
    Also reads timeout overrides from [settings] into the global constants.
    """
    global TIMEOUT_TLDR_DOWNLOAD, TIMEOUT_CHTSH_REQUEST, TIMEOUT_OLLAMA_API
    data = _load_toml(CONFIG_PATH)
    settings = data.get("settings", {})
    if "timeout_tldr"   in settings: TIMEOUT_TLDR_DOWNLOAD = int(settings["timeout_tldr"])
    if "timeout_chtsh"  in settings: TIMEOUT_CHTSH_REQUEST = int(settings["timeout_chtsh"])
    if "timeout_ollama" in settings: TIMEOUT_OLLAMA_API    = int(settings["timeout_ollama"])
    return data


def _provider_from_config(name: str, cfg_data: dict) -> ProviderConfig | None:
    """Builds a ProviderConfig from a named [provider.<name>] block."""
    block = cfg_data.get("provider", {}).get(name)
    if not block:
        return None
    protocol = block.get("protocol", "openai")
    return ProviderConfig(
        name     = name,
        protocol = protocol,
        model    = block.get("model", KNOWN_PROVIDERS.get(name, {}).get("default_model", "")),
        api_key  = block.get("api_key") or None,
        base_url = block.get("base_url") or KNOWN_PROVIDERS.get(name, {}).get("base_url"),
    )


def list_models(cfg: ProviderConfig) -> list[str]:
    """
    Fetches the model list from the provider's API.
    Returns a sorted list of model ID strings.
    """
    if cfg.protocol == "ollama":
        host = (cfg.base_url or "http://localhost:11434").rstrip("/")
        with urllib.request.urlopen(f"{host}/api/tags", timeout=10) as r:
            data = json.loads(r.read())
        return sorted(m["name"] for m in data.get("models", []))

    if cfg.protocol == "anthropic":
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": cfg.api_key or "",
                     "anthropic-version": "2023-06-01"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        return sorted(m["id"] for m in data.get("data", []))

    # OpenAI-compat: GET /models
    base = (cfg.base_url or "https://api.openai.com/v1").rstrip("/")
    req = urllib.request.Request(
        f"{base}/models",
        headers={"Authorization": f"Bearer {cfg.api_key or ''}"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
    return sorted(m["id"] for m in data.get("data", []))




# ─── OS Detection ─────────────────────────────────────────────────────────────

def _detect_os() -> dict:
    """
    Returns structured OS info used to filter tldr pages and cheat.sh results.
    Keys: system, distro, tldr_target, pkg_manager, wrong_platform_patterns
    """
    system = platform.system().lower()  # "linux", "darwin", "windows"
    distro = ""
    pkg_manager = ""

    if system == "linux":
        try:
            with open("/etc/os-release") as f:
                info = dict(
                    line.strip().split("=", 1)
                    for line in f if "=" in line
                )
            distro = info.get("ID", "").strip('"').lower()       # "fedora", "ubuntu", "arch"
            distro_like = info.get("ID_LIKE", "").strip('"').lower()

            # Map distro → package manager
            if distro in ("fedora", "rhel", "centos", "rocky", "alma") or "fedora" in distro_like or "rhel" in distro_like:
                pkg_manager = "dnf"
            elif distro in ("ubuntu", "debian", "linuxmint", "pop") or "debian" in distro_like or "ubuntu" in distro_like:
                pkg_manager = "apt"
            elif distro in ("arch", "manjaro", "endeavouros") or "arch" in distro_like:
                pkg_manager = "pacman"
            elif distro in ("opensuse", "suse") or "suse" in distro_like:
                pkg_manager = "zypper"
            elif distro == "alpine":
                pkg_manager = "apk"
            else:
                pkg_manager = "apt"  # safe fallback for unknown Linux
        except OSError:
            distro = "linux"
            pkg_manager = "apt"

        tldr_target = "linux"
        # Patterns that indicate a command is for the wrong platform
        wrong_platform_patterns = [
            r'\bdel\b', r'rmdir\s+/s', r'Remove-Item', r'Get-\w+', r'Set-\w+',   # Windows
            r'%APPDATA%', r'%USERPROFILE%', r'\.exe\b', r'\.bat\b',               # Windows
            r'\bbrew\b', r'\bopen\s+-a\b', r'\.app\b', r'\bpbcopy\b',             # macOS
        ]

    elif system == "darwin":
        distro = "macos"
        pkg_manager = "brew"
        tldr_target = "osx"
        wrong_platform_patterns = [
            r'\bdel\b', r'rmdir\s+/s', r'Remove-Item', r'Get-\w+', r'Set-\w+',   # Windows
            r'%APPDATA%', r'%USERPROFILE%', r'\.exe\b', r'\.bat\b',               # Windows
            r'\bapt\b', r'\bdnf\b', r'\bpacman\b', r'\byum\b',                    # Linux pkg managers
        ]

    elif system == "windows":
        distro = "windows"
        pkg_manager = "winget"
        tldr_target = "windows"
        wrong_platform_patterns = [
            r'\bsudo\b', r'\bapt\b', r'\bdnf\b', r'\bpacman\b',                   # Linux
            r'\brm\s+-', r'\bchmod\b', r'\bchown\b', r'\bkill\s+-', r'\bgrep\b', # Linux-only flags
            r'\bbrew\b',                                                            # macOS
        ]
    else:
        distro = system
        pkg_manager = ""
        tldr_target = "common"
        wrong_platform_patterns = []

    return {
        "system":   system,
        "distro":   distro,
        "pkg_manager": pkg_manager,
        "tldr_target": tldr_target,
        "wrong_platform_patterns": wrong_platform_patterns,
    }


def _is_wrong_platform(command: str, os_info: dict) -> bool:
    """Returns True if the command contains patterns that indicate it's for the wrong OS."""
    for pattern in os_info.get("wrong_platform_patterns", []):
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False


def _fix_pkg_manager(command: str, os_info: dict) -> str:
    """
    Replaces wrong package manager references with the correct one for this distro.
    e.g. on Fedora: 'apt install foo' → 'dnf install foo'
    """
    pm = os_info.get("pkg_manager", "")
    if not pm:
        return command
    # Map of managers to replace → with the correct one
    all_managers = ["apt-get", "apt", "dnf", "yum", "pacman", "zypper", "apk", "brew"]
    for other in all_managers:
        if other != pm and re.search(rf'\b{re.escape(other)}\b', command):
            command = re.sub(rf'\b{re.escape(other)}\b', pm, command)
    return command



def _strip_unresolved_placeholders(command: str) -> str:
    """
    If tldr/cht.sh left {{placeholders}} we couldn't fill, return "" so the
    cascade falls through — prevents things like: virsh pool-delete --pool {{name|uuid}}
    being handed raw to the shell.
    """
    if re.search(r'\{\{.+?\}\}', command):
        return ""
    return command


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
        # Replace <file>, <path> etc. angle-bracket placeholders
        command = re.sub(
            r'<(?:file|filename|path|archive|directory|source|target)[^>]*>', 
            safe_file, 
            command, 
            flags=re.IGNORECASE
        )
        # Replace {{file}}, {{filename}}, {{path}}, {{name}}, {{source}}, {{target}}
        # tldr-style placeholders where we can safely substitute a real filename
        command = re.sub(
            r'\{\{(?:file(?:name)?|path|source|target|name|archive|directory)[^}]*\}\}',
            safe_file,
            command,
            flags=re.IGNORECASE
        )
    return command


def _build_lookup_tables(os_info: dict) -> tuple[dict[str, list[str]], set[str]]:
    """
    Returns (SYNONYMS, COMMON_COMMANDS) tuned to the user's OS and distro.
    Keeping these large and accurate is the key to good tldr matching without an LLM.
    """
    distro  = os_info.get("distro", "")
    system  = os_info.get("system", "linux")
    pkg_mgr = os_info.get("pkg_manager", "")

    # ── Universal synonyms (apply on all platforms) ──────────────────────────
    SYNONYMS: dict[str, list[str]] = {
        # Deletion / removal
        "delete":      ["remove", "rm", "erase", "unlink", "del", "trash", "wipe", "purge"],
        "remove":      ["delete", "rm", "erase", "unlink", "uninstall", "purge", "wipe"],
        "erase":       ["delete", "remove", "rm", "wipe", "clear"],
        "wipe":        ["delete", "remove", "erase", "clear", "shred"],
        "unlink":      ["delete", "remove", "rm"],
        "trash":       ["delete", "remove", "rm"],
        "purge":       ["remove", "delete", "uninstall", "clean"],

        # Process management
        "kill":        ["terminate", "stop", "end", "pkill", "killall", "abort", "quit", "exit"],
        "terminate":   ["kill", "stop", "end", "pkill", "abort"],
        "stop":        ["kill", "terminate", "end", "halt", "pause", "suspend"],
        "pause":       ["stop", "suspend", "freeze"],
        "suspend":     ["pause", "stop", "freeze"],
        "restart":     ["reboot", "reload", "reset", "bounce"],
        "reboot":      ["restart", "reset", "reload"],
        "reload":      ["restart", "refresh", "reboot"],

        # Display / listing
        "show":        ["display", "list", "print", "view", "output", "dump", "cat", "reveal"],
        "display":     ["show", "list", "print", "view", "output"],
        "list":        ["show", "display", "print", "enumerate", "ls"],
        "view":        ["show", "display", "cat", "less", "more", "open"],
        "print":       ["show", "display", "echo", "cat"],
        "output":      ["show", "display", "print", "dump"],
        "dump":        ["show", "print", "output", "cat", "export"],
        "reveal":      ["show", "display", "find", "locate"],
        "enumerate":   ["list", "show", "display"],
        "watch":       ["monitor", "observe", "tail", "follow"],
        "monitor":     ["watch", "tail", "follow", "observe"],
        "tail":        ["follow", "watch", "monitor"],
        "follow":      ["tail", "watch", "monitor"],

        # Search / finding
        "find":        ["search", "locate", "grep", "look", "seek", "query", "detect"],
        "search":      ["find", "locate", "grep", "look", "seek", "query"],
        "locate":      ["find", "search", "grep", "which"],
        "grep":        ["search", "find", "filter", "match", "look"],
        "look":        ["find", "search", "locate", "grep"],
        "seek":        ["find", "search", "locate"],
        "filter":      ["grep", "search", "find", "exclude", "select"],
        "match":       ["grep", "find", "search", "filter"],
        "detect":      ["find", "locate", "check", "identify"],
        "identify":    ["find", "detect", "locate", "which"],

        # File operations
        "copy":        ["cp", "duplicate", "clone", "replicate", "backup"],
        "cp":          ["copy", "duplicate", "clone"],
        "duplicate":   ["copy", "cp", "clone", "replicate"],
        "clone":       ["copy", "duplicate", "cp", "replicate", "download", "git"],
        "move":        ["mv", "rename", "relocate", "transfer"],
        "mv":          ["move", "rename", "relocate"],
        "rename":      ["mv", "move"],
        "relocate":    ["move", "mv", "transfer"],
        "transfer":    ["move", "copy", "cp", "scp", "rsync", "send"],
        "sync":        ["rsync", "backup", "transfer", "copy"],
        "backup":      ["copy", "cp", "rsync", "sync", "archive", "tar"],

        # Compression / archiving
        "compress":    ["zip", "tar", "gzip", "bzip2", "xz", "archive", "pack", "deflate"],
        "archive":     ["tar", "zip", "compress", "pack", "backup"],
        "pack":        ["tar", "zip", "compress", "archive"],
        "zip":         ["compress", "archive", "pack", "gzip"],
        "extract":     ["unzip", "untar", "decompress", "tar", "expand", "unpack"],
        "unzip":       ["extract", "decompress", "tar", "unpack", "expand"],
        "unpack":      ["extract", "unzip", "untar", "decompress", "expand"],
        "expand":      ["extract", "unzip", "unpack", "decompress"],
        "decompress":  ["extract", "unzip", "untar", "gunzip", "unpack"],

        # Creation
        "make":        ["create", "mkdir", "touch", "new", "init", "generate", "build"],
        "create":      ["make", "mkdir", "touch", "new", "init", "generate"],
        "new":         ["create", "make", "touch", "mkdir", "init"],
        "init":        ["create", "make", "new", "initialize", "setup"],
        "initialize":  ["init", "create", "setup", "new"],
        "generate":    ["create", "make", "new", "produce"],
        "build":       ["make", "compile", "generate", "create"],
        "compile":     ["build", "make", "gcc", "cc"],

        # Editing / modification
        "edit":        ["modify", "change", "update", "patch", "fix", "alter", "write"],
        "modify":      ["edit", "change", "update", "alter", "patch"],
        "change":      ["edit", "modify", "update", "alter"],
        "update":      ["upgrade", "modify", "edit", "refresh", "patch"],
        "upgrade":     ["update", "install", "dist-upgrade", "full-upgrade"],
        "patch":       ["update", "fix", "edit", "modify"],
        "fix":         ["repair", "patch", "update", "restore"],
        "repair":      ["fix", "restore", "recover"],

        # Permissions / ownership
        "permissions": ["chmod", "chown", "acl", "rights", "access"],
        "chmod":       ["permissions", "rights", "access"],
        "chown":       ["ownership", "permissions", "user", "group"],
        "ownership":   ["chown", "permissions", "user", "group"],

        # Networking
        "ping":        ["test", "check", "reachable", "connect", "network"],
        "check":       ["verify", "test", "status", "ping", "validate", "inspect"],
        "verify":      ["check", "test", "validate", "confirm"],
        "test":        ["check", "verify", "ping", "validate"],
        "connect":     ["ssh", "telnet", "nc", "curl", "ping"],
        "download":    ["wget", "curl", "fetch", "pull", "get"],
        "fetch":       ["download", "wget", "curl", "pull", "get"],
        "get":         ["download", "fetch", "wget", "curl", "pull"],
        "pull":        ["download", "fetch", "get", "git", "sync"],
        "upload":      ["send", "push", "scp", "rsync", "transfer"],
        "send":        ["upload", "push", "scp", "transfer", "curl"],
        "push":        ["upload", "send", "git", "scp", "publish"],
        "request":     ["curl", "wget", "fetch", "http"],
        "http":        ["curl", "wget", "request", "fetch"],
        "port":        ["lsof", "ss", "netstat", "socket", "listen"],
        "socket":      ["port", "lsof", "ss", "netstat"],
        "listen":      ["port", "lsof", "ss", "netstat", "socket"],
        "firewall":    ["iptables", "ufw", "firewalld", "nftables"],
        "route":       ["ip", "netstat", "routing", "network"],
        "dns":         ["dig", "nslookup", "host", "resolve"],
        "resolve":     ["dns", "dig", "nslookup", "host"],
        "proxy":       ["curl", "ssh", "tunnel", "forward"],
        "tunnel":      ["ssh", "proxy", "forward", "vpn"],
        "vpn":         ["openvpn", "wireguard", "tunnel"],

        # Disk / storage
        "disk":        ["df", "du", "mount", "fdisk", "lsblk", "storage"],
        "storage":     ["df", "du", "disk", "mount", "lsblk"],
        "space":       ["df", "du", "disk", "free", "usage"],
        "usage":       ["du", "df", "space", "top", "free"],
        "free":        ["space", "df", "du", "memory", "available"],
        "mount":       ["disk", "storage", "fstab", "loop"],
        "unmount":     ["umount", "eject", "detach"],
        "umount":      ["unmount", "eject", "detach"],
        "partition":   ["fdisk", "parted", "disk", "lsblk"],
        "format":      ["mkfs", "fdisk", "partition", "disk", "awk", "sed", "printf"],

        # System / services
        "service":     ["systemctl", "service", "daemon", "unit"],
        "daemon":      ["service", "systemctl", "background", "process"],
        "enable":      ["start", "activate", "systemctl", "service"],
        "disable":     ["stop", "deactivate", "systemctl", "service"],
        "status":      ["check", "show", "systemctl", "ps", "service"],
        "log":         ["journalctl", "syslog", "tail", "log", "history", "commits", "git"],
        "logs":        ["journalctl", "syslog", "tail", "log"],
        "journal":     ["journalctl", "log", "syslog"],
        "boot":        ["systemctl", "grub", "startup", "init"],
        "startup":     ["boot", "enable", "systemctl", "autostart"],
        "shutdown":    ["halt", "poweroff", "reboot", "stop"],
        "halt":        ["shutdown", "poweroff", "stop"],
        "poweroff":    ["shutdown", "halt", "stop"],
        "sleep":       ["suspend", "hibernate", "pm-suspend"],
        "hibernate":   ["sleep", "suspend", "pm-hibernate"],
        "user":        ["useradd", "usermod", "passwd", "who", "whoami", "id"],
        "group":       ["groupadd", "groupmod", "groups", "id"],
        "password":    ["passwd", "chpasswd", "auth"],
        "login":       ["su", "ssh", "auth", "passwd"],
        "logout":      ["exit", "su", "kill"],

        # Package management (generic)
        "install":     ["add", "get", "download", "setup", "pkg"],
        "uninstall":   ["remove", "delete", "purge", "pkg"],
        "package":     ["install", "pkg", "module", "dependency"],
        "dependency":  ["package", "install", "requires"],
        "cache":       ["clean", "clear", "refresh", "update"],
        "repo":        ["repository", "source", "ppa", "remote"],
        "repository":  ["repo", "source", "remote"],

        # Version control (git)
        "commit":      ["save", "snapshot", "record", "git"],
        "merge":       ["combine", "join", "integrate", "git"],
        "branch":      ["checkout", "fork", "git"],
        "checkout":    ["switch", "branch", "git"],
        "stash":       ["save", "shelve", "git"],
        "revert":      ["undo", "reset", "rollback", "git"],
        "undo":        ["revert", "reset", "rollback"],
        "rollback":    ["revert", "undo", "reset"],
        "diff":        ["compare", "changes", "git"],
        "compare":     ["diff", "git"],
        "tag":         ["release", "version", "mark", "git"],
        "history":     ["log", "commits", "git"],

        # Execution / running
        "run":         ["execute", "start", "launch", "exec", "call"],
        "execute":     ["run", "start", "launch", "exec", "call"],
        "start":       ["run", "execute", "launch", "systemctl", "begin"],
        "launch":      ["run", "execute", "start", "open"],
        "open":        ["launch", "start", "run", "xdg-open", "cat", "view"],
        "call":        ["run", "execute", "invoke"],
        "invoke":      ["call", "run", "execute"],
        "schedule":    ["cron", "crontab", "at", "timer"],
        "cron":        ["schedule", "crontab", "timer", "periodic"],
        "automate":    ["cron", "crontab", "script", "schedule"],

        # Text processing
        "replace":     ["sed", "awk", "tr", "substitute"],
        "substitute":  ["replace", "sed", "tr"],
        "sort":        ["order", "arrange", "organize"],
        "order":       ["sort", "arrange"],
        "count":       ["wc", "grep", "count"],
        "split":       ["cut", "awk", "divide", "separate"],
        "join":        ["cat", "paste", "combine", "merge"],
        "combine":     ["cat", "join", "paste", "merge"],
        "parse":       ["awk", "grep", "sed", "jq", "cut"],
        "encode":      ["base64", "openssl", "convert"],
        "decode":      ["base64", "openssl", "convert"],
        "encrypt":     ["gpg", "openssl", "ssl", "secure"],
        "decrypt":     ["gpg", "openssl", "ssl"],
        "hash":        ["md5sum", "sha256sum", "checksum", "digest"],
        "checksum":    ["md5sum", "sha256sum", "hash", "verify"],

        # Resource monitoring
        "cpu":         ["top", "htop", "ps", "mpstat", "load"],
        "memory":      ["free", "top", "htop", "ps", "ram"],
        "ram":         ["memory", "free", "top", "htop"],
        "load":        ["top", "htop", "uptime", "cpu"],
        "process":     ["ps", "top", "htop", "kill", "pgrep"],
        "processes":   ["ps", "top", "htop", "kill", "pgrep"],
        "thread":      ["ps", "top", "htop"],
        "job":         ["ps", "jobs", "bg", "fg"],

        # Environment
        "environment": ["env", "export", "printenv", "set"],
        "variable":    ["env", "export", "printenv", "set"],
        "path":        ["which", "env", "export", "find"],
        "alias":       ["bash", "zsh", "shell", "function"],
        "shell":       ["bash", "zsh", "sh", "fish", "dash"],
        "script":      ["bash", "sh", "python", "run", "execute"],
        "profile":     ["bashrc", "zshrc", "source", "env"],
        "config":      ["edit", "configure", "settings", "setup"],
        "configure":   ["config", "setup", "settings", "edit"],
        "settings":    ["config", "configure", "edit"],
        "setup":       ["install", "configure", "init", "config"],
    }

    # ── Base common commands (universal Linux/Unix) ───────────────────────────
    BASE_COMMON = {
        # Core file ops
        "rm", "cp", "mv", "ls", "ll", "la", "find", "locate", "which", "whereis",
        "cat", "less", "more", "head", "tail", "tac", "file", "stat", "touch",
        "mkdir", "rmdir", "ln", "readlink", "realpath", "basename", "dirname",
        "tree", "du", "df", "lsblk", "mount", "umount", "fdisk", "parted",

        # Text processing
        "grep", "egrep", "fgrep", "ripgrep", "rg", "sed", "awk", "gawk", "cut",
        "sort", "uniq", "wc", "tr", "tee", "echo", "printf", "xargs",
        "diff", "patch", "comm", "join", "paste", "column", "fold",
        "strings", "hexdump", "od", "xxd", "jq", "yq", "xmllint",

        # Compression
        "tar", "gzip", "gunzip", "bzip2", "bunzip2", "xz", "unxz",
        "zip", "unzip", "7z", "zstd", "lz4", "rar", "unrar",

        # Process management
        "ps", "top", "htop", "btop", "kill", "pkill", "killall", "pgrep",
        "nice", "renice", "nohup", "jobs", "bg", "fg", "wait",
        "strace", "ltrace", "lsof", "fuser", "pstree",

        # Networking
        "ping", "ping6", "traceroute", "tracepath", "mtr",
        "curl", "wget", "ssh", "scp", "sftp", "rsync",
        "ip", "ifconfig", "ss", "netstat", "nmap", "nc", "ncat", "socat",
        "dig", "nslookup", "host", "whois", "arp",
        "iptables", "ip6tables", "nftables", "ufw",
        "tcpdump", "wireshark", "tshark",
        "ftp", "telnet", "openssl", "gpg",

        # System info
        "uname", "hostname", "uptime", "date", "timedatectl", "hwclock",
        "free", "vmstat", "iostat", "sar", "dmesg", "lshw", "lscpu",
        "lspci", "lsusb", "inxi", "neofetch", "fastfetch",
        "env", "printenv", "export", "set", "source",
        "id", "who", "whoami", "w", "last", "lastlog",

        # User management
        "useradd", "userdel", "usermod", "passwd", "chpasswd",
        "groupadd", "groupdel", "groupmod", "groups", "id",
        "su", "sudo", "visudo", "chroot",

        # File permissions
        "chmod", "chown", "chgrp", "umask", "getfacl", "setfacl",

        # Disk / filesystem
        "mkfs", "fsck", "tune2fs", "badblocks", "blkid", "lsblk",
        "fdisk", "gdisk", "parted", "mkswap", "swapon", "swapoff",
        "dd", "pv", "shred", "wipe",

        # Shells and scripting
        "bash", "zsh", "sh", "fish", "dash", "ksh",
        "python", "python3", "pip", "pip3",
        "node", "npm", "npx", "yarn",
        "ruby", "gem", "perl", "lua", "go", "cargo", "rustc",
        "make", "cmake", "gcc", "g++", "cc", "ld",
        "cron", "crontab", "at", "atq", "atrm",
        "screen", "tmux", "byobu",

        # Version control
        "git", "svn", "hg",

        # Editors
        "vim", "vi", "nvim", "nano", "emacs", "micro", "helix",

        # Containers / virtualisation
        "docker", "podman", "buildah", "skopeo",
        "kubectl", "helm", "minikube", "kind",
        "vagrant", "virsh", "qemu",   # virsh is still known, just lower priority

        # Misc utilities
        "watch", "time", "timeout", "sleep", "yes", "seq", "shuf",
        "bc", "expr", "test", "true", "false",
        "base64", "md5sum", "sha1sum", "sha256sum", "sha512sum",
        "gpg", "openssl", "certbot",
        "cmp", "md5", "cksum",
        "xdg-open", "xclip", "xsel",
    }

    # ── Distro-specific additions ─────────────────────────────────────────────

    # Fedora / RHEL / CentOS / Rocky / AlmaLinux
    FEDORA_COMMANDS = {
        "dnf", "dnf5", "rpm", "rpm2cpio",
        "dnf-automatic", "subscription-manager",
        "firewall-cmd", "firewalld",
        "semanage", "setsebool", "setenforce", "getenforce", "restorecon", "chcon",
        "audit2allow", "ausearch", "auditctl",
        "systemctl", "journalctl", "loginctl", "localectl", "timedatectl",
        "nmcli", "nmtui", "NetworkManager",
        "cockpit", "insights-client",
        "flatpak", "rpm-ostree",
        "podman", "buildah", "skopeo",
        "grubby", "grub2-mkconfig",
        "dracut", "mkinitrd",
    }
    FEDORA_SYNONYMS = {
        "install":     ["dnf install", "dnf5 install", "rpm -i", "flatpak install"],
        "uninstall":   ["dnf remove", "dnf5 remove", "rpm -e", "flatpak uninstall"],
        "update":      ["dnf update", "dnf5 update", "dnf upgrade", "dnf-automatic"],
        "upgrade":     ["dnf upgrade", "dnf5 upgrade", "dnf update"],
        "search":      ["dnf search", "dnf5 search", "rpm -q", "find", "grep"],
        "package":     ["dnf", "dnf5", "rpm", "flatpak"],
        "selinux":     ["semanage", "setsebool", "setenforce", "restorecon", "chcon"],
        "security":    ["semanage", "firewall-cmd", "audit2allow", "openssl"],
        "firewall":    ["firewall-cmd", "firewalld", "iptables", "nftables"],
        "repo":        ["dnf config-manager", "dnf repolist", "dnf copr"],
        "copr":        ["dnf copr", "repo", "repository"],
        "service":     ["systemctl", "journalctl", "firewall-cmd"],
    }

    # Ubuntu / Debian / Mint / Pop!_OS
    DEBIAN_COMMANDS = {
        "apt", "apt-get", "apt-cache", "dpkg", "dpkg-query",
        "aptitude", "apt-file", "apt-mark",
        "add-apt-repository", "apt-key",
        "snap", "snapd", "snapcraft",
        "ufw",
        "update-alternatives", "update-rc.d", "invoke-rc.d",
        "debconf-set-selections", "dpkg-reconfigure",
        "gdebi", "tasksel",
        "lsb-release", "do-release-upgrade",
        "needrestart", "unattended-upgrades",
        "systemctl", "journalctl",
        "nmcli", "nmtui",
        "netplan",
    }
    DEBIAN_SYNONYMS = {
        "install":   ["apt install", "apt-get install", "dpkg -i", "snap install"],
        "uninstall": ["apt remove", "apt purge", "apt-get remove", "dpkg -r"],
        "update":    ["apt update", "apt upgrade", "apt-get update", "unattended-upgrades"],
        "upgrade":   ["apt upgrade", "apt full-upgrade", "do-release-upgrade"],
        "search":    ["apt search", "apt-cache search", "dpkg -l", "find"],
        "package":   ["apt", "apt-get", "dpkg", "snap"],
        "firewall":  ["ufw", "iptables", "nftables"],
        "repo":      ["add-apt-repository", "apt-key", "sources.list"],
        "ppa":       ["add-apt-repository", "repo", "repository"],
        "snap":      ["snapcraft", "snapd", "snap"],
        "service":   ["systemctl", "update-rc.d", "invoke-rc.d"],
    }

    # Arch Linux / Manjaro / EndeavourOS / Garuda
    ARCH_COMMANDS = {
        "pacman", "paru", "yay", "trizen", "pikaur", "aura",
        "makepkg", "pkgbuild", "namcap",
        "reflector", "rankmirrors",
        "pacstrap", "genfstab", "arch-chroot",
        "mkinitcpio", "dracut",
        "systemctl", "journalctl",
        "archinstall",
        "flatpak",
    }
    ARCH_SYNONYMS = {
        "install":   ["pacman -S", "paru -S", "yay -S", "makepkg -si"],
        "uninstall": ["pacman -R", "pacman -Rs", "pacman -Rns", "paru -R"],
        "update":    ["pacman -Syu", "paru -Syu", "yay -Syu"],
        "upgrade":   ["pacman -Syu", "paru -Syu"],
        "search":    ["pacman -Ss", "paru -Ss", "yay -Ss", "pacman -Q"],
        "package":   ["pacman", "paru", "yay", "makepkg"],
        "aur":       ["paru", "yay", "trizen", "makepkg"],
        "mirror":    ["reflector", "rankmirrors", "pacman"],
        "service":   ["systemctl", "journalctl"],
        "repo":      ["pacman.conf", "pacman", "reflector"],
    }

    # openSUSE / SUSE
    SUSE_COMMANDS = {
        "zypper", "rpm", "rpm2cpio",
        "yast", "yast2",
        "systemctl", "journalctl",
        "firewall-cmd", "SuSEfirewall2",
        "snapper",
        "zypper-download",
        "obs",
    }
    SUSE_SYNONYMS = {
        "install":   ["zypper install", "zypper in", "rpm -i"],
        "uninstall": ["zypper remove", "zypper rm", "rpm -e"],
        "update":    ["zypper update", "zypper up", "zypper patch"],
        "search":    ["zypper search", "zypper se", "rpm -q"],
        "package":   ["zypper", "rpm", "yast"],
        "snapshot":  ["snapper", "btrfs", "snapper create"],
        "service":   ["systemctl", "yast", "firewall-cmd"],
    }

    # Alpine Linux
    ALPINE_COMMANDS = {
        "apk", "apk-tools",
        "rc-service", "rc-update", "openrc",
        "busybox",
    }
    ALPINE_SYNONYMS = {
        "install":   ["apk add"],
        "uninstall": ["apk del"],
        "update":    ["apk update", "apk upgrade"],
        "search":    ["apk search", "apk info"],
        "package":   ["apk"],
        "service":   ["rc-service", "rc-update", "openrc"],
    }

    # macOS
    MACOS_COMMANDS = {
        "brew", "mas", "port",
        "open", "pbcopy", "pbpaste",
        "defaults", "plutil", "plistbuddy",
        "launchctl", "launchd",
        "diskutil", "hdiutil",
        "security", "codesign", "spctl",
        "xcode-select", "xcrun",
        "caffeinate", "pmset",
        "networksetup", "scutil",
        "mdfind", "mdls", "mdutil",   # Spotlight
        "osascript", "automator",
        "say", "afplay",
        "sw_vers", "system_profiler",
        "sips", "qlmanage",
        "tmutil",                      # Time Machine
        "csrutil",
        "softwareupdate",
        "dscl",                        # Directory Services
    }
    MACOS_SYNONYMS = {
        "install":   ["brew install", "mas install", "softwareupdate -i"],
        "uninstall": ["brew uninstall", "brew remove", "mas uninstall"],
        "update":    ["brew update", "brew upgrade", "softwareupdate -i"],
        "upgrade":   ["brew upgrade", "softwareupdate -i"],
        "search":    ["brew search", "mdfind", "find", "grep"],
        "package":   ["brew", "mas", "port"],
        "open":      ["open", "xdg-open"],
        "clipboard": ["pbcopy", "pbpaste"],
        "service":   ["launchctl", "brew services"],
        "disk":      ["diskutil", "hdiutil", "df", "du"],
        "spotlight": ["mdfind", "mdls", "mdutil"],
        "plist":     ["defaults", "plutil", "plistbuddy"],
        "font":      ["brew", "fontforge"],
        "security":  ["security", "codesign", "spctl", "csrutil"],
        "screenshot": ["screencapture"],
    }

    # Windows
    WINDOWS_COMMANDS = {
        "del", "copy", "move", "dir", "type", "echo",
        "mkdir", "rmdir", "ren", "cls",
        "tasklist", "taskkill", "sc", "net",
        "reg", "regedit",
        "ipconfig", "netsh", "ping", "tracert", "nslookup",
        "winget", "choco", "scoop",
        "powershell", "pwsh",
        "wsl", "wslconfig",
        "sfc", "dism", "bcdedit",
    }
    WINDOWS_SYNONYMS = {
        "install":   ["winget install", "choco install", "scoop install"],
        "uninstall": ["winget uninstall", "choco uninstall"],
        "update":    ["winget upgrade", "choco upgrade", "scoop update"],
        "search":    ["winget search", "dir", "where"],
        "package":   ["winget", "choco", "scoop"],
        "delete":    ["del", "Remove-Item", "rmdir"],
        "list":      ["dir", "Get-ChildItem"],
        "copy":      ["copy", "xcopy", "robocopy", "Copy-Item"],
        "move":      ["move", "Move-Item"],
        "service":   ["sc", "net start", "net stop", "Get-Service"],
        "firewall":  ["netsh advfirewall", "New-NetFirewallRule"],
        "process":   ["tasklist", "taskkill", "Get-Process"],
    }

    # ── Assemble distro-specific tables ──────────────────────────────────────
    extra_commands: set[str] = set()
    extra_synonyms: dict[str, list[str]] = {}

    if system == "linux":
        if distro in ("fedora", "rhel", "centos", "rocky", "alma", "redhat"):
            extra_commands = FEDORA_COMMANDS
            extra_synonyms = FEDORA_SYNONYMS
        elif distro in ("ubuntu", "debian", "linuxmint", "pop", "elementary",
                        "kali", "parrot", "raspbian", "devuan"):
            extra_commands = DEBIAN_COMMANDS
            extra_synonyms = DEBIAN_SYNONYMS
        elif distro in ("arch", "manjaro", "endeavouros", "garuda", "artix",
                        "blackarch", "crystalinux"):
            extra_commands = ARCH_COMMANDS
            extra_synonyms = ARCH_SYNONYMS
        elif distro in ("opensuse", "suse", "opensuse-tumbleweed", "opensuse-leap"):
            extra_commands = SUSE_COMMANDS
            extra_synonyms = SUSE_SYNONYMS
        elif distro == "alpine":
            extra_commands = ALPINE_COMMANDS
            extra_synonyms = ALPINE_SYNONYMS
        else:
            # Unknown Linux — add all Linux package managers so something works
            extra_commands = {"apt", "dnf", "pacman", "zypper", "apk", "snap", "flatpak"}

    elif system == "darwin":
        extra_commands = MACOS_COMMANDS
        extra_synonyms = MACOS_SYNONYMS

    elif system == "windows":
        extra_commands = WINDOWS_COMMANDS
        extra_synonyms = WINDOWS_SYNONYMS

    # Merge synonym tables — distro-specific entries override/extend base ones
    merged_synonyms = {**SYNONYMS}
    for k, v in extra_synonyms.items():
        if k in merged_synonyms:
            merged_synonyms[k] = list(set(merged_synonyms[k] + v))
        else:
            merged_synonyms[k] = v

    merged_commands = BASE_COMMON | extra_commands

    return merged_synonyms, merged_commands


def call_tldr(query: str, context: str = "", os_info: dict | None = None) -> str:
    """
    Queries a local, offline cache of tldr pages.
    Downloads the database on the first run if it doesn't exist.
    """
    if os_info is None:
        os_info = _detect_os()

    cache_dir = Path.home() / ".cache" / "woman" / "tldr"
    if not cache_dir.exists():
        try:
            print(f"{DIM}Downloading local tldr database for the first time...{RESET}".ljust(60), file=sys.stderr, end="\r")
            url = "https://github.com/tldr-pages/tldr/releases/latest/download/tldr.zip"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=TIMEOUT_TLDR_DOWNLOAD) as response:
                data = response.read()
            cache_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                z.extractall(cache_dir)
        except (urllib.error.URLError, zipfile.BadZipFile):
            return ""

    pages_dir = cache_dir / "pages"
    if not pages_dir.exists():
        return ""

    tldr_target = os_info["tldr_target"]
    # Search platform-specific folder first, then common.
    # Never search other platforms' folders — no Windows commands on Linux.
    targets = [tldr_target, "common"] if tldr_target != "common" else ["common"]

    SYNONYMS, COMMON_COMMANDS = _build_lookup_tables(os_info)

    raw_query_words = set(re.findall(r'\w+', query.lower()))
    expanded_query_words = set(raw_query_words)
    for w in raw_query_words:
        expanded_query_words.update(SYNONYMS.get(w, []))

    best_match_cmd = ""
    best_score = 0

    for t in targets:
        target_dir = pages_dir / t
        if not target_dir.exists(): continue

        # Platform-specific pages get a bonus over generic common pages
        platform_bonus = 2 if t == tldr_target and tldr_target != "common" else 0

        for page in target_dir.glob("*.md"):
            try:
                with open(page, 'r', encoding='utf-8') as f:
                    content = f.read()
                lines = content.splitlines()

                title_words = set(re.findall(r'\w+', page.stem.lower()))
                title_score = 3 if title_words & expanded_query_words else 0
                common_bonus = 2 if title_words & COMMON_COMMANDS else 0

                for i, line in enumerate(lines):
                    if line.startswith(">"):
                        desc = line[1:].strip().lower()
                        desc_words = set(re.findall(r'\w+', desc))
                        score = title_score + common_bonus + platform_bonus + len(expanded_query_words.intersection(desc_words))

                        if score > best_score and score >= max(1, len(raw_query_words) // 2):
                            for j in range(i + 1, len(lines)):
                                if lines[j].startswith("`"):
                                    candidate = lines[j].strip("` ")
                                    # Skip commands that are for a different OS
                                    if _is_wrong_platform(candidate, os_info):
                                        break
                                    best_score = score
                                    best_match_cmd = candidate
                                    break
            except OSError:
                continue

    if best_match_cmd:
        best_match_cmd = _fix_pkg_manager(best_match_cmd, os_info)
        result = inject_context(best_match_cmd, context, query)
        return _strip_unresolved_placeholders(result)

    return ""

def call_chtsh(query: str, context: str = "", os_info: dict | None = None) -> str:
    """Queries cheat.sh as a no-key web fallback, with OS-aware filtering."""
    if os_info is None:
        os_info = _detect_os()

    # Append OS hint so cheat.sh returns platform-appropriate results
    os_hint = os_info["distro"] or os_info["system"]  # e.g. "fedora", "linux", "macos"
    slug = urllib.parse.quote_plus(f"{query} {os_hint}")
    # ~ prefix = natural language search mode
    url = f"https://cht.sh/~{slug}?QT"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_CHTSH_REQUEST) as response:
            text = response.read().decode('utf-8')
            lines = text.splitlines()
            # Walk through all returned commands, skip any that are for the wrong OS
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if _is_wrong_platform(line, os_info):
                    continue
                line = _fix_pkg_manager(line, os_info)
                result = inject_context(line, context, query)
                result = _strip_unresolved_placeholders(result)
                if result:
                    return result
    except urllib.error.URLError:
        pass
    return ""




# ─── Context Gathering ────────────────────────────────────────────────────────

def gather_context(os_info: dict | None = None) -> str:
    """Gathers OS details, directory contents, and shell history to feed the AI.
    Accepts a pre-computed os_info dict to avoid calling _detect_os() twice."""
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
        if platform.system() == "Windows":
            ls_cmd = ["cmd", "/c", "dir", "/a", "/b"]
        else:
            ls_cmd = ["ls", "-a"]
        result = subprocess.run(ls_cmd, capture_output=True, text=True, timeout=5)
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
    """Attempts to read the last 'n' lines from the user's shell history.
    Supports bash, zsh, fish, and PowerShell."""
    candidates = []
    histfile = os.environ.get("HISTFILE")
    if histfile:
        candidates.append(Path(histfile).expanduser())
    candidates += [
        Path.home() / ".bash_history",
        Path.home() / ".zsh_history",
        Path.home() / ".history",
        # fish stores one command per file — we read the data file instead
        Path.home() / ".local" / "share" / "fish" / "fish_history",
        # PowerShell (Windows & cross-platform)
        Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt",
        Path.home() / ".local" / "share" / "powershell" / "PSReadLine" / "ConsoleHost_history.txt",
        Path.home() / ".config"  / "powershell" / "PSReadLine" / "ConsoleHost_history.txt",
    ]

    for path in candidates:
        if path.exists():
            try:
                raw  = path.read_bytes()
                text = raw.decode("utf-8", errors="replace")
                commands: list[str] = []
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    # zsh extended history: ": 1234567890:0;actual command"
                    if line.startswith(": ") and ";" in line:
                        line = line.split(";", 1)[1]
                    # fish history: "- cmd: actual command" lines
                    if line.startswith("- cmd:"):
                        line = line[len("- cmd:"):].strip()
                    elif line.startswith("  when:"):
                        continue  # skip fish timestamp lines
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

def _ollama_reachable() -> bool:
    """Returns True if Ollama's default port is open and responding."""
    import socket
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    # Strip scheme for socket check
    host_clean = host.replace("http://", "").replace("https://", "")
    hostname, _, port_str = host_clean.partition(":")
    port = int(port_str) if port_str else 11434
    try:
        with socket.create_connection((hostname, port), timeout=1):
            return True
    except OSError:
        return False


def _resolve_provider(
    cfg_data: dict,
    cli_provider: str | None = None,
    cli_model: str | None = None,
) -> ProviderConfig | None:
    """
    Determines which LLM backend to use. Priority order:
      1. -p / --provider CLI flag  (must name a [provider.<name>] in config)
      2. WOMAN_PROVIDER env var    (same)
      3. [defaults] provider in config file
      4. Auto-sniff legacy env vars: OPENAI_API_KEY, ANTHROPIC_API_KEY
      5. Ollama reachability check
      6. None  →  tldr / cht.sh cascade only
    """
    model_override = cli_model or os.environ.get("WOMAN_MODEL")

    def _with_model(pc: ProviderConfig) -> ProviderConfig:
        if model_override:
            pc.model = model_override
        return pc

    # ── 1 & 2: explicit provider name ─────────────────────────────────────────
    provider_name = cli_provider or os.environ.get("WOMAN_PROVIDER", "")
    if provider_name:
        pc = _provider_from_config(provider_name.lower(), cfg_data)
        if pc:
            return _with_model(pc)
        print(f"{YELLOW}⚠ Provider '{provider_name}' not found in config. "
              f"Run: woman config{RESET}", file=sys.stderr)

    # ── 3: config file default ─────────────────────────────────────────────────
    default_name = cfg_data.get("defaults", {}).get("provider", "")
    if default_name:
        pc = _provider_from_config(default_name, cfg_data)
        if pc:
            return _with_model(pc)

    # ── 4: legacy env var sniffing (backward-compatible) ─────────────────────
    if os.environ.get("OPENAI_API_KEY"):
        return _with_model(ProviderConfig(
            name="openai", protocol="openai", model=model_override or "gpt-4o",
            api_key=os.environ["OPENAI_API_KEY"],
            base_url="https://api.openai.com/v1",
        ))
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _with_model(ProviderConfig(
            name="anthropic", protocol="anthropic", model=model_override or "claude-sonnet-4-6",
            api_key=os.environ["ANTHROPIC_API_KEY"],
        ))
    if os.environ.get("WOMAN_API_KEY"):
        # Generic env-var: pair with WOMAN_PROVIDER / WOMAN_BASE_URL / WOMAN_PROTOCOL
        return _with_model(ProviderConfig(
            name     = "env",
            protocol = os.environ.get("WOMAN_PROTOCOL", "openai"),
            model    = model_override or os.environ.get("WOMAN_MODEL", ""),
            api_key  = os.environ["WOMAN_API_KEY"],
            base_url = os.environ.get("WOMAN_BASE_URL"),
        ))

    # ── 5: Ollama auto-detect ─────────────────────────────────────────────────
    if os.environ.get("OLLAMA_HOST") or shutil.which("ollama") or _ollama_reachable():
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        return _with_model(ProviderConfig(
            name="ollama", protocol="ollama",
            model=model_override or "llama3.2",
            base_url=host,
        ))

    # ── 6: no LLM available ────────────────────────────────────────────────────
    return None



# ─── Subcommands ──────────────────────────────────────────────────────────────

def cmd_models(args: argparse.Namespace, cfg_data: dict) -> None:
    """
    woman models [--provider NAME]
    Lists models available for the given (or default) provider.
    """
    provider_name = getattr(args, "provider", None)
    if provider_name:
        pc = _provider_from_config(provider_name, cfg_data)
        if not pc:
            _die(f"Provider '{provider_name}' not found in config. Run: woman config")
    else:
        pc = _resolve_provider(cfg_data)
        if not pc:
            _die("No provider configured. Run: woman config")

    print(f"{DIM}Fetching models for {pc.name} ({pc.protocol})...{RESET}", file=sys.stderr)
    try:
        models = list_models(pc)
    except Exception as e:
        _die(f"Could not fetch model list: {e}")
        return

    print(f"\n{BOLD}{CYAN}Available models for {pc.name}:{RESET}")
    for i, m in enumerate(models, 1):
        marker = f" {GREEN}← current{RESET}" if m == pc.model else ""
        print(f"  {DIM}{i:>3}.{RESET}  {m}{marker}")
    print(f"\n{DIM}To use a model: woman -m <model-id> ...{RESET}")
    print(f"{DIM}To save it:     add  model = \"<model-id>\"  to {CONFIG_PATH}{RESET}\n")


def cmd_config(args: argparse.Namespace) -> None:
    """
    woman config  — interactive setup wizard.
    Adds a new provider entry to ~/.config/woman/config.toml.
    """
    cfg_data = load_config()

    print(f"\n{BOLD}{CYAN}woman — Provider Setup Wizard{RESET}")
    print(f"{DIM}Config file: {CONFIG_PATH}{RESET}\n")

    # ── Pick provider type ────────────────────────────────────────────────────
    known_names = list(KNOWN_PROVIDERS.keys())
    print("Available provider types:")
    for i, name in enumerate(known_names, 1):
        info = KNOWN_PROVIDERS[name]
        url  = info["base_url"] or "(you supply the URL)"
        print(f"  {DIM}{i:>2}.{RESET}  {BOLD}{name:<12}{RESET}  {DIM}{url}{RESET}")

    while True:
        raw = input(f"\nProvider type (name or number, default=openai): ").strip()
        if not raw:
            raw = "openai"
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(known_names):
                chosen_type = known_names[idx]
                break
        elif raw in KNOWN_PROVIDERS:
            chosen_type = raw
            break
        print(f"{YELLOW}  Not recognised. Try again.{RESET}")

    info = KNOWN_PROVIDERS[chosen_type]

    # ── Label for this entry ─────────────────────────────────────────────────
    default_label = chosen_type
    label = input(f"Label for this entry [{default_label}]: ").strip() or default_label

    # ── API key ───────────────────────────────────────────────────────────────
    api_key: str | None = None
    if chosen_type != "ollama" and chosen_type != "lmstudio":
        api_key = getpass.getpass(f"API key (input hidden): ").strip() or None
        if not api_key:
            print(f"{YELLOW}  No key entered — you can add it later.{RESET}")

    # ── Base URL ──────────────────────────────────────────────────────────────
    default_url = info["base_url"] or ""
    if chosen_type == "custom":
        base_url = input(f"Base URL (e.g. https://your-endpoint/v1): ").strip() or None
    else:
        entered = input(f"Base URL [{default_url}]: ").strip()
        base_url = entered or default_url or None

    # ── Protocol ──────────────────────────────────────────────────────────────
    default_protocol = info["protocol"]
    if chosen_type == "custom":
        raw_p = input(f"Protocol [openai/anthropic/ollama, default={default_protocol}]: ").strip()
        protocol = raw_p if raw_p in ("openai", "anthropic", "ollama") else default_protocol
    else:
        protocol = default_protocol

    # ── Model selection ───────────────────────────────────────────────────────
    default_model = info["default_model"]
    probe_pc = ProviderConfig(
        name=label, protocol=protocol, model=default_model,
        api_key=api_key, base_url=base_url,
    )

    want_browse = input(f"\nFetch model list from API to choose? (y/N): ").strip().lower()
    chosen_model = default_model
    if want_browse in ("y", "yes"):
        try:
            print(f"{DIM}Connecting to {base_url or 'provider API'}...{RESET}", end="", flush=True)
            models = list_models(probe_pc)
            print(f"\r{' '*60}\r", end="")
            print(f"\n{BOLD}Available models:{RESET}")
            for i, m in enumerate(models[:40], 1):   # cap at 40 lines
                print(f"  {DIM}{i:>3}.{RESET}  {m}")
            if len(models) > 40:
                print(f"  {DIM}… and {len(models)-40} more{RESET}")
            raw_m = input(f"\nModel (name or number) [{default_model}]: ").strip()
            if raw_m.isdigit():
                idx = int(raw_m) - 1
                chosen_model = models[idx] if 0 <= idx < len(models) else default_model
            elif raw_m:
                chosen_model = raw_m
        except Exception as e:
            print(f"\n{YELLOW}  Could not fetch models: {e}{RESET}")
            raw_m = input(f"Model ID [{default_model}]: ").strip()
            chosen_model = raw_m or default_model
    else:
        raw_m = input(f"Model ID [{default_model}]: ").strip()
        chosen_model = raw_m or default_model

    # ── Set as default? ───────────────────────────────────────────────────────
    existing_default = cfg_data.get("defaults", {}).get("provider", "")
    make_default = input(
        f"\nSet '{label}' as the default provider? "
        f"{'(currently: ' + existing_default + ') ' if existing_default else ''}(Y/n): "
    ).strip().lower()
    set_default = make_default not in ("n", "no")

    # ── Write config ──────────────────────────────────────────────────────────
    cfg_data.setdefault("provider", {})[label] = {
        k: v for k, v in {
            "protocol": protocol,
            "model":    chosen_model,
            "api_key":  api_key or "",
            "base_url": base_url or "",
        }.items()
    }
    if set_default:
        cfg_data.setdefault("defaults", {})["provider"] = label

    _save_toml(CONFIG_PATH, cfg_data)

    print(f"\n{GREEN}✓{RESET} Saved to {CONFIG_PATH}")
    if set_default:
        print(f"{GREEN}✓{RESET} Default provider set to '{label}'")
    print(f"\n{DIM}Test it with:  woman list files in current directory{RESET}\n")


def cmd_list_providers(cfg_data: dict) -> None:
    """woman config --list — prints all configured providers."""
    providers = cfg_data.get("provider", {})
    default   = cfg_data.get("defaults", {}).get("provider", "")
    if not providers:
        print(f"{YELLOW}No providers configured yet.{RESET}  Run: woman config")
        return
    print(f"\n{BOLD}{CYAN}Configured providers:{RESET}  ({CONFIG_PATH})\n")
    for name, block in providers.items():
        marker = f"  {GREEN}[default]{RESET}" if name == default else ""
        key    = block.get("api_key", "")
        hint   = f"sk-...{key[-4:]}" if len(key) > 4 else ("(set)" if key else "(not set)")
        print(f"  {BOLD}{name}{RESET}{marker}")
        print(f"      protocol={block.get('protocol','?')}  "
              f"model={block.get('model','?')}  "
              f"key={hint}  "
              f"url={block.get('base_url','(default)')}")
    print()


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
               f"  woman -p groq summarize system logs\n"
               f"  woman config\n"
               f"  woman models"
    )

    subparsers = parser.add_subparsers(dest="subcommand")

    # ── woman config ──────────────────────────────────────────────────────────
    config_parser = subparsers.add_parser(
        "config", help="Add or manage LLM provider configurations"
    )
    config_parser.add_argument(
        "--list", action="store_true", help="List all configured providers"
    )

    # ── woman models ──────────────────────────────────────────────────────────
    models_parser = subparsers.add_parser(
        "models", help="List models available for a configured provider"
    )
    models_parser.add_argument(
        "--provider", "-p", help="Provider name from config (default: auto-resolve)"
    )

    # ── woman <query> ─────────────────────────────────────────────────────────
    parser.add_argument("query", nargs="*", help="What you want to do in natural language")
    parser.add_argument(
        "-p", "--provider",
        help="Provider name from config or a known provider (e.g. groq, anthropic)"
    )
    parser.add_argument(
        "-m", "--model",
        help="Override the model (e.g. gpt-4o, llama3, claude-opus-4-6)"
    )
    parser.add_argument(
        "--list-providers", action="store_true",
        help="List all configured providers and exit"
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s v{__version__}")

    args = parser.parse_args()

    # ── Load config once ──────────────────────────────────────────────────────
    cfg_data = load_config()

    # ── Route subcommands ─────────────────────────────────────────────────────
    if args.subcommand == "config":
        if args.list:
            cmd_list_providers(cfg_data)
        else:
            cmd_config(args)
        return

    if args.subcommand == "models":
        cmd_models(args, cfg_data)
        return

    if getattr(args, "list_providers", False):
        cmd_list_providers(cfg_data)
        return

    if not args.query:
        parser.print_help()
        sys.exit(0)

    query = " ".join(args.query)

    _print_banner()
    print(f"{DIM}Gathering context...{RESET}", file=sys.stderr, end="\r")

    # ── Detect OS once, pass everywhere ───────────────────────────────────────
    os_info = _detect_os()
    context = gather_context(os_info)

    provider_cfg = _resolve_provider(cfg_data, getattr(args, "provider", None), getattr(args, "model", None))

    command = ""
    failed_reason = ""

    # ── CASCADE TIER 1: LLM ───────────────────────────────────────────────────
    if provider_cfg:
        print(f"{DIM}Asking {provider_cfg.name} ({provider_cfg.model})...        {RESET}",
              file=sys.stderr, end="\r")
        try:
            raw_response = _dispatch_provider(query, context, provider_cfg)
            command = _extract_command(raw_response, os_info)
        except KeyboardInterrupt:
            print("\nAborted.", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            raw = str(e)
            if "401" in raw or "authentication" in raw.lower() or "api_key" in raw.lower():
                failed_reason = "invalid or missing API key"
            elif "429" in raw or "rate" in raw.lower():
                failed_reason = "rate limit hit"
            elif "timeout" in raw.lower() or "timed out" in raw.lower():
                failed_reason = "request timed out"
            elif "connect" in raw.lower() or "network" in raw.lower():
                failed_reason = "connection error"
            elif "model" in raw.lower() and ("not found" in raw.lower() or "pull" in raw.lower()):
                failed_reason = f"model not found — run: ollama pull {provider_cfg.model}"
            else:
                failed_reason = f"{type(e).__name__}: {raw[:80]}"
            print(f"\n{YELLOW}⚠ LLM failed ({provider_cfg.name}): {failed_reason}{RESET}", file=sys.stderr)
            print(f"{DIM}Falling back to tldr/cheat.sh...{RESET}", file=sys.stderr)

    # ── CASCADE TIER 2: Local tldr (offline, fast) ───────────────────────────
    if not command:
        print(f"{DIM}Searching local tldr manuals...{RESET}".ljust(60), file=sys.stderr, end="\r")
        command = call_tldr(query, context, os_info)

    # ── CASCADE TIER 3: cheat.sh (no-key web fallback) ───────────────────────
    if not command:
        print(f"{DIM}Searching cheat.sh internet fallback...{RESET}".ljust(60), file=sys.stderr, end="\r")
        command = call_chtsh(query, context, os_info)

    if not command:
        print(" " * 60, file=sys.stderr, end="\r")
        hint = "Run: woman config" if not provider_cfg else "Try rephrasing your query."
        _die(f"All backends failed to find a matching command. {hint}")

    # ── Sanitise markdown artifacts ───────────────────────────────────────────
    print(" " * 60, file=sys.stderr, end="\r")
    command = command.strip()
    if command.startswith("```"):
        command = "\n".join(command.splitlines()[1:])
    if command.endswith("```"):
        command = "\n".join(command.splitlines()[:-1])
    command = command.strip().strip("`").strip()

    # ── Present & confirm ─────────────────────────────────────────────────────
    print(f"\n  {CYAN}{BOLD}{command}{RESET}\n")
    try:
        answer = input(f"{YELLOW}Execute this command? (y/n): {RESET}").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print(f"\n{DIM}Aborted.{RESET}")
        sys.exit(0)

    if answer in ("y", "yes"):
        print()
        try:
            if platform.system() == "Windows":
                result = subprocess.run(["powershell", "-Command", command], text=True)
            else:
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
