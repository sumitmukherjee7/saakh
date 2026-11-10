#!/usr/bin/env bash
# Saakh: one-command setup & run (macOS / Linux / Git Bash)
#   ./run.sh          setup + train (if needed) + build UI + serve on http://127.0.0.1:8000
#   ./run.sh test     run the test-suite
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"; elif [ -x "$ROOT/.venv/Scripts/python.exe" ]; then PY="$ROOT/.venv/Scripts/python.exe"; else
  python3 -m venv "$ROOT/.venv" || python -m venv "$ROOT/.venv"
  PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="$ROOT/.venv/Scripts/python.exe"
  "$PY" -m pip install --upgrade pip && "$PY" -m pip install -r "$ROOT/backend/requirements.txt"
fi
export PYTHONIOENCODING=utf-8
cd "$ROOT/backend"
if [ "${1:-}" = "test" ]; then exec "$PY" -m pytest -q; fi
[ -f saakh/risk/artifacts/scorecard.json ] || "$PY" -m saakh.risk.train
if [ ! -f "$ROOT/frontend/dist/index.html" ]; then (cd "$ROOT/frontend" && npm install --no-audit --no-fund && npm run build); fi
exec "$PY" -m uvicorn saakh.api.main:app --app-dir "$ROOT/backend" --host 127.0.0.1 --port 8000
