#!/usr/bin/env bash
# Cloudbase Self-Healing Startup Script

# Stop on error
set -e

# --- Configuratie ---
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$INSTALL_DIR/backend"
VENV_PATH="$BACKEND_DIR/venv"
PORT=7823
CREDS="$HOME/.pdmanager/credentials"
APP_NAME="Cloudbase"
CLI_NAME="cloudbase"
SERVICE_NAME="cloudbase"
COMMAND="up"

# Kleuren voor de logs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

usage() {
    cat <<'EOF'
Usage: ./start.sh [command]

Commands:
    up          Start Cloudbase (default)
    down        Stop the running systemd service
    restart     Restart the running systemd service
    status      Show service status
    logs        Show service logs
    enable      Install/update the systemd service and enable boot autostart
    disable     Disable boot autostart and stop the service
  help        Show this help text

Examples:
    ./start.sh up
    cloudbase enable
    cloudbase status
EOF
}

if [[ $# -gt 0 ]]; then
    COMMAND="$1"
fi

require_systemctl() {
    if ! command -v systemctl >/dev/null 2>&1; then
        echo -e "${RED}>>> systemctl is not available on this machine.${RESET}"
        exit 1
    fi
}

write_service_file() {
    require_systemctl
    local run_user
    run_user="${SUDO_USER:-$(id -un)}"
    sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" > /dev/null <<EOF
[Unit]
Description=${APP_NAME}
After=network.target

[Service]
Type=simple
User=${run_user}
WorkingDirectory=${INSTALL_DIR}
ExecStart=/bin/bash ${INSTALL_DIR}/start.sh up
Restart=on-failure
RestartSec=5
KillMode=none
TimeoutStopSec=15
Delegate=yes

[Install]
WantedBy=multi-user.target
EOF
}

case "$COMMAND" in
    help|-h|--help)
        usage
        exit 0
        ;;
    enable|autostart)
        write_service_file
        sudo systemctl daemon-reload
        sudo systemctl enable --now "${SERVICE_NAME}.service"
        echo -e "${GREEN}>>> ${APP_NAME} now starts automatically on boot.${RESET}"
        echo -e "${GREEN}>>> Use '${CLI_NAME} status' to inspect the service.${RESET}"
        exit 0
        ;;
    disable)
        require_systemctl
        sudo systemctl disable --now "${SERVICE_NAME}.service"
        echo -e "${GREEN}>>> Boot autostart disabled for ${APP_NAME}.${RESET}"
        exit 0
        ;;
    status)
        require_systemctl
        systemctl status "${SERVICE_NAME}" --no-pager
        exit $?
        ;;
    stop|down)
        require_systemctl
        sudo systemctl stop "${SERVICE_NAME}"
        exit $?
        ;;
    restart)
        require_systemctl
        sudo systemctl restart "${SERVICE_NAME}"
        exit $?
        ;;
    logs)
        require_systemctl
        sudo journalctl -u "${SERVICE_NAME}" -n 100 --no-pager
        exit $?
        ;;
    start|up)
        ;;
    *)
        echo -e "${RED}>>> Unknown command: $COMMAND${RESET}"
        usage
        exit 1
        ;;
esac

detect_pkg_mgr() {
    if command -v apt-get >/dev/null 2>&1; then
        echo "apt"
    elif command -v dnf >/dev/null 2>&1; then
        echo "dnf"
    elif command -v yum >/dev/null 2>&1; then
        echo "yum"
    elif command -v pacman >/dev/null 2>&1; then
        echo "pacman"
    elif command -v zypper >/dev/null 2>&1; then
        echo "zypper"
    else
        echo ""
    fi
}

install_missing_runtime_deps() {
    local pkg_mgr="$1"

    case "$pkg_mgr" in
        apt)
            sudo apt-get update
            sudo apt-get install -y lsof python3-venv python3-pip
            ;;
        dnf)
            sudo dnf install -y lsof python3 python3-pip
            ;;
        yum)
            sudo yum install -y lsof python3 python3-pip
            ;;
        pacman)
            sudo pacman -S --noconfirm lsof python python-pip
            ;;
        zypper)
            sudo zypper install -y lsof python3 python3-pip
            ;;
        *)
            echo -e "${RED}>>> Could not detect a supported package manager. Please install python3, python3-venv, python3-pip and lsof manually.${RESET}"
            exit 1
            ;;
    esac
}

port_owner_pid() {
    local pid=""
    if command -v lsof >/dev/null 2>&1; then
        pid=$(lsof -ti tcp:"$PORT" 2>/dev/null | head -n 1 || true)
    elif command -v ss >/dev/null 2>&1; then
        pid=$(ss -lptn "sport = :$PORT" 2>/dev/null | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | head -n 1)
    fi
    echo "$pid"
}

echo -e "${GREEN}>>> Starting ${APP_NAME} initialization...${RESET}"

# 1. Check of we de nodige systeem pakketten hebben
if ! command -v python3 &> /dev/null || ! python3 -m venv --help &> /dev/null 2>&1 || ! command -v lsof &> /dev/null; then
    echo -e "${YELLOW}>>> Missing system dependencies. Installing...${RESET}"
    install_missing_runtime_deps "$(detect_pkg_mgr)"
fi

# 2. Map voor credentials aanmaken
mkdir -p "$(dirname "$CREDS")"

# 3. Oude processen opruimen op poort 7823
OLD_PID=$(port_owner_pid)
if [ -n "$OLD_PID" ]; then
    echo -e "${YELLOW}>>> Cleaning up old process (PID: $OLD_PID)...${RESET}"
    kill -9 "$OLD_PID" 2>/dev/null || sudo kill -9 "$OLD_PID" || true
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
exec "$VENV_PATH/bin/uvicorn" main:app --host 0.0.0.0 --port "$PORT" \
  --timeout-graceful-shutdown 8