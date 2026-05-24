#!/usr/bin/env bash
set -euo pipefail

# ─── ArtiPivot Dev Starter (macOS / Linux) ───

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT_DIR/.pids"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

cleanup() {
    if [ -f "$PID_FILE" ]; then
        while IFS= read -r pid; do
            kill "$pid" 2>/dev/null || true
        done < "$PID_FILE"
        rm -f "$PID_FILE"
    fi
}
trap cleanup EXIT

# ─── Check dependencies ───
command -v python3 >/dev/null 2>&1 || { error "Python3 not found. Install it first."; exit 1; }
command -v node >/dev/null 2>&1    || { error "Node.js not found. Install it first."; exit 1; }
command -v npm >/dev/null 2>&1     || { error "npm not found. Install it first."; exit 1; }

# ─── Install dependencies if needed ───
if [ ! -d "$ROOT_DIR/.venv" ] && [ ! -d "$ROOT_DIR/node_modules" ]; then
    info "Installing Python dependencies..."
    cd "$ROOT_DIR" && uv sync --dev
fi

if [ ! -d "$ROOT_DIR/web/node_modules" ]; then
    info "Installing frontend dependencies..."
    cd "$ROOT_DIR/web" && npm install
fi

# ─── Start backend ───
info "Starting FastAPI backend on :8000..."
cd "$ROOT_DIR"
uv run artipivot serve &
BACKEND_PID=$!
echo "$BACKEND_PID" >> "$PID_FILE"

# Wait for backend
for i in $(seq 1 30); do
    if curl -s http://127.0.0.1:8000/health >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

if ! curl -s http://127.0.0.1:8000/health >/dev/null 2>&1; then
    error "Backend failed to start"
    exit 1
fi
info "Backend ready"

# ─── Start frontend ───
info "Starting Vite dev server on :5173..."
cd "$ROOT_DIR/web"
npx vite --host &
FRONTEND_PID=$!
echo "$FRONTEND_PID" >> "$PID_FILE"

# Wait for frontend
for i in $(seq 1 30); do
    if curl -s http://127.0.0.1:5173 >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

info "========================================="
info "  ArtiPivot is running!"
info "  Frontend:  http://localhost:5173"
info "  Backend:   http://localhost:8000"
info "  API docs:  http://localhost:8000/docs"
info ""
info "  Press Ctrl+C to stop"
info "========================================="

# Keep script running
wait
