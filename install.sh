#!/usr/bin/env bash
set -euo pipefail

BOLD='\033[1m'
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="Cloudbase"
CLI_NAME="cloudbase"
LEGACY_CLI_NAME="pdmanager"
SERVICE_NAME="cloudbase"
LOG_DIR="$HOME/.cloudbase/logs"
LOG_FILE="$LOG_DIR/cloudbase-install.log"

mkdir -p "$LOG_DIR"

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

log_line() {
  local level="$1"
  local color="$2"
  local message="$3"
  printf '[%s] [%s] %s\n' "$(timestamp)" "$level" "$message" >> "$LOG_FILE"
  printf '%b[%s] [%s]%b %s\n' "$color" "$(timestamp)" "$level" "$RESET" "$message"
}

info()    { log_line "INFO" "$BLUE" "$1"; }
success() { log_line "OK"   "$GREEN" "$1"; }
warn()    { log_line "WARN" "$YELLOW" "$1"; }
err()     { log_line "ERR"  "$RED" "$1"; }

banner() {
  cat <<'EOF'
_________ .__                   .______.                         
\_   ___ \|  |   ____  __ __  __| _/\_ |__ _____    ______ ____  
/    \  \/|  |  /  _ \|  |  \/ __ |  | __ \\__  \  /  ___// __ \ 
\     \___|  |_(  <_> )  |  / /_/ |  | \_\ \/ __ \_\___ \\  ___/ 
 \______  /____/\____/|____/\____ |  |___  (____  /____  >\___  >
        \/                       \/      \/     \/     \/     \/ 
EOF
}

usage() {
  cat <<'EOF'
Usage: ./install.sh

Cloudbase installs the full production stack by default:
  - system packages
  - nginx
  - Python virtual environment
  - /usr/local/bin/cloudbase CLI
  - systemd service with boot autostart

Supported legacy flags (accepted for compatibility):
  -y, --yes, --with-nginx, --with-service, --with-cli
  -h, --help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes|--with-nginx|--with-service|--with-cli)
      warn "Ignoring legacy flag '$1' - Cloudbase install now always performs the full setup."
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      err "Unknown option: $1"
      echo ""
      usage
      exit 1
      ;;
  esac
  shift
done

printf '\n%b' "$BOLD"
banner
printf '%b\n' "$RESET"
info "Starting full Cloudbase installation"
info "Installer log: $LOG_FILE"

PKG_MGR=""
if   command -v apt-get &>/dev/null; then PKG_MGR="apt"
elif command -v dnf     &>/dev/null; then PKG_MGR="dnf"
elif command -v yum     &>/dev/null; then PKG_MGR="yum"
elif command -v pacman  &>/dev/null; then PKG_MGR="pacman"
elif command -v zypper  &>/dev/null; then PKG_MGR="zypper"
fi

ensure_pkg_index() {
  if [[ -n "${PKG_INDEX_READY:-}" ]]; then
    return
  fi
  case "$PKG_MGR" in
    apt)
      info "Refreshing apt package index"
      sudo apt-get update
      ;;
  esac
  PKG_INDEX_READY=1
}

install_pkg() {
  local name="$1" apt_pkg="$2" dnf_pkg="$3" pac_pkg="$4" zy_pkg="$5"
  info "Installing $name"
  case "$PKG_MGR" in
    apt)
      ensure_pkg_index
      sudo apt-get install -y $apt_pkg
      ;;
    dnf)
      sudo dnf install -y "$dnf_pkg"
      ;;
    yum)
      sudo yum install -y "$dnf_pkg"
      ;;
    pacman)
      sudo pacman -S --noconfirm "$pac_pkg"
      ;;
    zypper)
      sudo zypper install -y "$zy_pkg"
      ;;
    *)
      err "$name not found and no supported package manager detected"
      err "Install $name manually and re-run this script"
      exit 1
      ;;
  esac
  success "$name installed"
}

if command -v python3 &>/dev/null; then
  success "Python found: $(python3 --version)"
else
  install_pkg "Python 3" "python3 python3-pip python3-venv" \
                          "python3 python3-pip" \
                          "python python-pip" \
                          "python3 python3-pip"
fi

if [[ "$PKG_MGR" == "apt" ]] && ! python3 -m venv --help &>/dev/null 2>&1; then
  info "Installing python3-venv"
  ensure_pkg_index
  sudo apt-get install -y python3-venv
fi

if command -v lsof &>/dev/null; then
  success "lsof found"
else
  install_pkg "lsof" "lsof" "lsof" "lsof" "lsof"
fi

if command -v git &>/dev/null; then
  success "Git found: $(git --version)"
else
  install_pkg "Git" "git" "git" "git" "git"
fi

if command -v nginx &>/dev/null; then
  success "Nginx found"
else
  install_pkg "Nginx" "nginx" "nginx" "nginx" "nginx"
fi

info "Creating Cloudbase data directories"
mkdir -p "$HOME/.cloudbase/apps" "$HOME/.cloudbase/logs" "$HOME/.cloudbase/certs"

# Migrate data from old ~/.pdmanager if it exists and ~/.cloudbase is fresh
if [[ -d "$HOME/.pdmanager" && ! -f "$HOME/.cloudbase/cloudbase.db" ]]; then
  warn "Old ~/.pdmanager detected. Migrating data to ~/.cloudbase"
  [[ -f "$HOME/.pdmanager/pdmanager.db" ]]  && cp "$HOME/.pdmanager/pdmanager.db"  "$HOME/.cloudbase/cloudbase.db"
  [[ -f "$HOME/.pdmanager/credentials" ]]    && cp "$HOME/.pdmanager/credentials"    "$HOME/.cloudbase/credentials"
  [[ -f "$HOME/.pdmanager/secret_key" ]]     && cp "$HOME/.pdmanager/secret_key"     "$HOME/.cloudbase/secret_key"
  success "Migration complete (old ~/.pdmanager is kept as backup)"
fi

success "Data directories ready at ~/.cloudbase"

info "Preparing Cloudbase maintenance directory"
sudo mkdir -p /var/www/cloudbase/maintenance
sudo chmod 755 /var/www/cloudbase/maintenance
success "Maintenance directory ready at /var/www/cloudbase/maintenance"

info "Building Python virtual environment"
cd "$SCRIPT_DIR/backend"
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
success "Python dependencies installed"

CREDS="$HOME/.cloudbase/credentials"
if [[ ! -f "$CREDS" ]]; then
  info "Generating administrator password"
  mkdir -p "$(dirname "$CREDS")"
  CB_PASS=$(python3 -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits + '!@#%^&*') for _ in range(20)))")
  python3 - <<PYEOF
import sys
sys.path.insert(0, '.')
import auth
auth.save_hashed_password(auth.hash_password("$CB_PASS"))
PYEOF
  printf '%s' "$CB_PASS" > "$HOME/.cloudbase/.first-run-password"
  success "Administrator credentials saved"
fi

info "Installing Cloudbase CLI wrapper"
sudo tee "/usr/local/bin/${CLI_NAME}" > /dev/null <<EOF
#!/usr/bin/env bash
exec /bin/bash "$SCRIPT_DIR/start.sh" "\$@"
EOF
sudo chmod 755 "/usr/local/bin/${CLI_NAME}"
sudo tee "/usr/local/bin/${LEGACY_CLI_NAME}" > /dev/null <<EOF
#!/usr/bin/env bash
exec /usr/local/bin/${CLI_NAME} "\$@"
EOF
sudo chmod 755 "/usr/local/bin/${LEGACY_CLI_NAME}"
success "CLI installed at /usr/local/bin/${CLI_NAME}"

if command -v systemctl &>/dev/null; then
  USER_NAME="${SUDO_USER:-$(id -un)}"
  SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
  START_SH="$SCRIPT_DIR/start.sh"
  info "Installing systemd service"
  sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=${APP_NAME}
After=network.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$SCRIPT_DIR
ExecStart=/bin/bash $START_SH run
Restart=on-failure
RestartSec=5
KillMode=none
TimeoutStopSec=15
Delegate=yes

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable --now "${SERVICE_NAME}.service"
  success "Systemd service installed, enabled and started (${SERVICE_NAME}.service)"
else
  warn "systemd was not detected. Cloudbase was installed without boot autostart."
fi

printf '\n'
printf '%b%s%b\n' "$YELLOW" "================================================================" "$RESET"
printf '%b  Cloudbase installation complete%b\n' "$BOLD" "$RESET"
if [[ -n "${CB_PASS:-}" ]]; then
  printf '%b  Username : admin%b\n' "$BOLD" "$RESET"
  printf '%b  Password : %b%s%b\n' "$BOLD" "$GREEN" "$CB_PASS" "$RESET"
fi
printf '%b  Open at  : http://localhost:7823%b\n' "$BOLD" "$RESET"
printf '%b%s%b\n' "$YELLOW" "================================================================" "$RESET"
printf '\n'
printf 'Commands:\n'
printf '  %s start     - Start Cloudbase\n' "$CLI_NAME"
printf '  %s stop      - Stop Cloudbase\n' "$CLI_NAME"
printf '  %s status    - Show status\n' "$CLI_NAME"
printf '  %s logs      - View logs\n' "$CLI_NAME"
printf '  %s nginx <domain> - Set up nginx proxy\n' "$CLI_NAME"
printf '  %s help      - All commands\n' "$CLI_NAME"
printf '\n'
