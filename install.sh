#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT_DIR"

if [ "${1:-}" = "--dev" ]; then
  if command -v uv >/dev/null 2>&1; then
    uv pip install -e ".[ui,test]"
  else
    python3 -m pip install -e ".[ui,test]"
  fi
else
  if command -v uv >/dev/null 2>&1; then
    uv tool install --force --reinstall ".[ui]"
  else
    python3 -m pip install --user ".[ui]"
  fi
fi

echo ""
if command -v woman >/dev/null 2>&1; then
  echo "woman is installed. Run: woman --help"
else
  echo "Warning: 'woman' command not found on PATH."
  echo "Ensure your Python bin directory is in PATH."
  echo "  Typical locations: ~/.local/bin, ~/.venv/bin"
fi
