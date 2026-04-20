#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$SCRIPT_DIR/backend"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
BOLD='\033[1m'
RESET='\033[0m'

PORT=7823

echo -e "${BOLD}Starting Process & Deployment Manager…${RESET}\n"

cd "$BACKEND"
[ -f "venv/bin/activate" ] && source venv/bin/activate

echo -e "${GREEN}${BOLD}PDManager started${RESET}"
echo -e "  Panel: ${BLUE}http://localhost:${PORT}${RESET}"
echo -e "\nPress Ctrl+C to stop\n"

uvicorn main:app --host 0.0.0.0 --port "$PORT" --reload --reload-dir . --reload-include '*.py'
