#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# Polar-EmotiBit Analyzer — Single-command launcher
#
# Usage:  ./run.sh
#
# Starts the FastAPI backend (port 8000) and the Vite dev server
# (port 5173) together.  Open http://localhost:5173 in a browser.
# Press Ctrl-C to stop both.
# ──────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Check prerequisites ───────────────────────────────────────
command -v python3 >/dev/null 2>&1 || { echo "❌  Python 3 not found. Install from https://python.org"; exit 1; }
command -v node    >/dev/null 2>&1 || { echo "❌  Node.js not found. Install from https://nodejs.org (v18+)"; exit 1; }
command -v npm     >/dev/null 2>&1 || { echo "❌  npm not found. Comes with Node.js."; exit 1; }

echo "╔══════════════════════════════════════════════════╗"
echo "║  Polar-EmotiBit Analyzer                        ║"
echo "║  Starting backend + frontend…                   ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── Backend setup ─────────────────────────────────────────────
cd "$ROOT/backend"
if [ ! -d ".venv" ]; then
  echo "📦  Creating Python virtual environment…"
  python3 -m venv .venv
fi

echo "📦  Installing backend dependencies…"
.venv/bin/pip install -q -e ".[dev]"

echo "🚀  Starting backend (FastAPI) on http://localhost:8000"
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# ── Frontend setup ────────────────────────────────────────────
cd "$ROOT/frontend"
if [ ! -d "node_modules" ]; then
  echo "📦  Installing frontend dependencies…"
  npm install --silent 2>/dev/null
fi

echo "🚀  Starting frontend (Vite) on http://localhost:5173"
npm run dev -- --host 0.0.0.0 &
FRONTEND_PID=$!

# ── Wait + cleanup ────────────────────────────────────────────
echo ""
echo "✅  Both servers running."
echo "    → Open http://localhost:5173 in your browser"
echo "    → Press Ctrl-C to stop"
echo ""

cleanup() {
  echo ""
  echo "Shutting down…"
  kill $BACKEND_PID  2>/dev/null || true
  kill $FRONTEND_PID 2>/dev/null || true
  wait $BACKEND_PID  2>/dev/null || true
  wait $FRONTEND_PID 2>/dev/null || true
  echo "Done."
}
trap cleanup EXIT INT TERM

wait
