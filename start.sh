#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$SCRIPT_DIR/backend"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
RESET='\033[0m'

PORT=7823
CREDS="$HOME/.pdmanager/credentials"

echo -e "${BOLD}Starting Process & Deployment Manager…${RESET}\n"

# ── Kill any previous instance on this port ───────────────────────────────
OLD_PID=$(lsof -ti tcp:"$PORT" 2>/dev/null || true)
if [ -n "$OLD_PID" ]; then
  echo -e "Stopping previous instance (pid $OLD_PID)…"
  kill "$OLD_PID" 2>/dev/null || true
  sleep 1
fi

cd "$BACKEND"
[ -f "venv/bin/activate" ] && source venv/bin/activate

# ── Ensure Python dependencies are installed ──────────────────────────────
python3 -m pip install -q -r requirements.txt

# ── First-run: generate a random admin password ────────────────────────────
if [ ! -f "$CREDS" ]; then
  PASS=$(python3 -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits + '!@#%^&*') for _ in range(20)))")
  python3 - <<PYEOF
import os, sys
sys.path.insert(0, '.')
import auth
auth.save_hashed_password(auth.hash_password("$PASS"))
PYEOF
  echo -e "${YELLOW}${BOLD}╔════════════════════════════════════════╗${RESET}"
  echo -e "${YELLOW}${BOLD}║         FIRST-RUN ADMIN PASSWORD       ║${RESET}"
  echo -e "${YELLOW}${BOLD}╠════════════════════════════════════════╣${RESET}"
  echo -e "${YELLOW}${BOLD}║  Password: ${PASS}  ║${RESET}"
  echo -e "${YELLOW}${BOLD}╚════════════════════════════════════════╝${RESET}"
  echo -e "${YELLOW}Save this password — it will not be shown again.${RESET}\n"
fi

echo -e "${GREEN}${BOLD}PDManager started${RESET}"
echo -e "  Panel: ${BLUE}http://localhost:${PORT}${RESET}"
echo -e "\nPress Ctrl+C to stop\n"

uvicorn main:app --host 0.0.0.0 --port "$PORT" --reload --reload-dir . --reload-include '*.py'
