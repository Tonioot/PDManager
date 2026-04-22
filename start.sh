#!/usr/bin/env bash
# PDManager Self-Healing Startup Script

# Stop on error
set -e

# --- Configuratie ---
INSTALL_DIR="/home/tonio/PDManager"
BACKEND_DIR="$INSTALL_DIR/backend"
VENV_PATH="$BACKEND_DIR/venv"
PORT=7823
CREDS="/home/tonio/.pdmanager/credentials"

# Kleuren voor de logs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

echo -e "${GREEN}>>> Starting PDManager initialization...${RESET}"

# 1. Check of we de nodige systeem pakketten hebben
if ! command -v lsof &> /dev/null || ! dpkg -s python3-venv &> /dev/null; then
    echo -e "${YELLOW}>>> Missing system dependencies. Installing...${RESET}"
    sudo apt-get update
    sudo apt-get install -y lsof python3-venv python3-pip
fi

# 2. Map voor credentials aanmaken
mkdir -p "$(dirname "$CREDS")"

# 3. Oude processen opruimen op poort 7823
OLD_PID=$(sudo lsof -ti tcp:"$PORT" 2>/dev/null || true)
if [ -n "$OLD_PID" ]; then
    echo -e "${YELLOW}>>> Cleaning up old process (PID: $OLD_PID)...${RESET}"
    sudo kill -9 "$OLD_PID" || true
    sleep 1
fi

# 4. Naar backend map navigeren
cd "$BACKEND_DIR"

# 5. Virtual Environment (venv) controle en reparatie
if [ ! -d "$VENV_PATH" ] || [ ! -f "$VENV_PATH/bin/pip" ]; then
    echo -e "${YELLOW}>>> Venv missing or broken. Rebuilding...${RESET}"
    rm -rf "$VENV_PATH"
    python3 -m venv venv
    echo -e "${GREEN}>>> Venv created successfully.${RESET}"
fi

# 6. Dependencies installeren/updaten
echo -e "${GREEN}>>> Syncing python dependencies...${RESET}"
"$VENV_PATH/bin/pip" install --upgrade pip
"$VENV_PATH/bin/pip" install -r requirements.txt

# 7. Admin wachtwoord genereren bij eerste keer opstarten
if [ ! -f "$CREDS" ]; then
    echo -e "${YELLOW}>>> First run detected. Generating admin password...${RESET}"
    PASS=$("$VENV_PATH/bin/python3" -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits + '!@#%^&*') for _ in range(20)))")
    
    "$VENV_PATH/bin/python3" - <<PYEOF
import sys
sys.path.insert(0, '.')
import auth
auth.save_hashed_password(auth.hash_password("$PASS"))
PYEOF

    echo -e "${GREEN}******************************************"
    echo -e "   FIRST-RUN ADMIN PASSWORD: ${PASS}"
    echo -e "******************************************${RESET}"
fi

# 8. Start de applicatie
echo -e "${GREEN}>>> Launching Uvicorn server on port $PORT...${RESET}"
exec "$VENV_PATH/bin/uvicorn" main:app --host 0.0.0.0 --port "$PORT"