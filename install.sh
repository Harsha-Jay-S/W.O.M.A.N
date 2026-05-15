#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

cd "$ROOT_DIR"

if command -v uv >/dev/null 2>&1; then
  uv pip install -e .[ui]
else
  python3 -m pip install -e .[ui]
fi

echo "Installed woman_revamp. Run: python -m woman_revamp"
