#!/usr/bin/env bash
clear
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="$REPO_ROOT/.venv/Scripts/python.exe"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Python do ambiente virtual nao encontrado em: $PYTHON_BIN" >&2
    exit 1
fi

cd "$REPO_ROOT"

UVICORN_ARGS=(review_web.main:app --host "$HOST" --port "$PORT")

if [[ "${RELOAD:-0}" == "1" ]]; then
    UVICORN_ARGS+=(--reload)
fi

exec "$PYTHON_BIN" -m uvicorn "${UVICORN_ARGS[@]}"