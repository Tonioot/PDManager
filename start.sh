#!/usr/bin/env bash
set -e

# Gebruik absolute paden voor stabiliteit onder systemd
SCRIPT_DIR="/home/tonio/PDManager"
BACKEND="$SCRIPT_DIR/backend"
CREDS="/home/tonio/.pdmanager/credentials"
PORT=7823

# Kleuren voor output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
RESET='\033[0m'

echo -e "${BOLD}Starting Process & Deployment Manager…${RESET}\n"

# ── Map voor credentials aanmaken ──────────────────────────────────────────
mkdir -p "$(dirname "$CREDS")"

# ── Stop oude instanties (zonder te crashen als lsof mist) ─────────────────
if command -v lsof >/dev/null 2>&1; then
    OLD_PID=$(lsof -ti tcp:"$PORT" 2>/dev/null || true)
    if [ -n "$OLD_PID" ]; then
      echo -e "Stopping previous instance (pid $OLD_PID)…"
      kill "$OLD_PID" 2>/dev/null || true
      sleep 1
    fi
else
    echo -e "${YELLOW}Warning: lsof not found, skipping port check.${RESET}"
fi

cd "$BACKEND"

# ── Virtual Environment controle en setup ──────────────────────────────────
if [ ! -f "venv/bin/activate" ]; then
    echo -e "Creating virtual environment…"
    python3 -m venv venv
fi

# Gebruik de pip in de venv direct, dat is veiliger dan 'source' in scripts
./venv/bin/pip install -q -r requirements.txt

# ── First-run: generate a random admin password ────────────────────────────
if [ ! -f "$CREDS" ]; then
    # Genereer wachtwoord via de python in de venv
    PASS=$(./venv/bin/python3 -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits + '!@#%^&*') for _ in range(20)))")
    
    ./venv/bin/python3 - <<PYEOF
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
echo -e "   Panel: ${BLUE}http://localhost:${PORT}${RESET}"

# ── Start de applicatie via de venv uvicorn ────────────────────────────────
exec ./venv/bin/uvicorn main:app --host 0.0.0.0 --port "$PORT"