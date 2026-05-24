#!/usr/bin/env bash
set -euo pipefail

# ─── ArtiPivot Dev Stopper (macOS / Linux) ───

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT_DIR/.pids"

GREEN='\033[0;32m'
NC='\033[0m'

if [ ! -f "$PID_FILE" ]; then
    echo "No .pids file found. Is ArtiPivot running?"
    exit 0
fi

echo -e "${GREEN}[INFO]${NC}  Stopping ArtiPivot..."

while IFS= read -r pid; do
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null && echo "  Stopped PID $pid" || echo "  Failed to stop PID $pid"
    else
        echo "  PID $pid already stopped"
    fi
done < "$PID_FILE"

rm -f "$PID_FILE"
echo -e "${GREEN}[INFO]${NC}  All services stopped."
