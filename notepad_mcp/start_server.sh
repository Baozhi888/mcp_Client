#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"
export SERVER_MODE="${SERVER_MODE:-true}"

python3 --version
python3 notepad_mcp_fixed.py
