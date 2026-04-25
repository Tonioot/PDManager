#!/usr/bin/env bash
set -e

BOLD='\033[1m'
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
RESET='\033[0m'

info()    { echo -e "${BLUE}[INFO]${RESET} $1"; }
success() { echo -e "${GREEN}[OK]${RESET}   $1"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $1"; }
err()     { echo -e "${RED}[ERR]${RESET}  $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="Cloudbase"
CLI_NAME="cloudbase"
LEGACY_CLI_NAME="pdmanager"
SERVICE_NAME="cloudbase"

usage() {
  cat <<'EOF'
Usage: ./install.sh

Cloudbase always installs the full Linux stack:
  - system packages
  - nginx
  - Python virtual environment
  - /usr/local/bin/cloudbase CLI
  - systemd service with boot autostart

Supported legacy flags (now optional and ignored):
  -y, --yes, --with-nginx, --with-service, --with-cli
  -h, --help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes|--with-nginx|--with-service|--with-cli)
      warn "Ignoring legacy flag '$1' - Cloudbase install is now always full-stack."
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

echo -e "\n${BOLD}${APP_NAME} — Installer${RESET}\n"
info "Running full Cloudbase installation..."

# ── Detect package manager ────────────────────────────────────────────────────
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
      info "Refreshing apt package index…"
      sudo apt-get update
      ;;
  esac
  PKG_INDEX_READY=1
}

install_pkg() {
  # usage: install_pkg <display-name> <apt-pkg> <dnf-pkg> <pacman-pkg> <zypper-pkg>
  local name="$1" apt_pkg="$2" dnf_pkg="$3" pac_pkg="$4" zy_pkg="$5"
  info "Installing $name…"
  case "$PKG_MGR" in
    apt)
      ensure_pkg_index
      sudo apt-get install -y $apt_pkg
      ;;
    dnf)    sudo dnf install -y "$dnf_pkg" ;;
    yum)    sudo yum install -y "$dnf_pkg" ;;
    pacman) sudo pacman -S --noconfirm "$pac_pkg" ;;
    zypper) sudo zypper install -y "$zy_pkg" ;;
    *)
      err "$name not found and no supported package manager detected."
      err "Please install $name manually and re-run this script."
      exit 1
      ;;
  esac
  success "$name installed"
}

# ── Python ────────────────────────────────────────────────────────────────────
if command -v python3 &>/dev/null; then
  success "Python found: $(python3 --version)"
else
  install_pkg "Python 3" "python3 python3-pip python3-venv" \
                          "python3 python3-pip" \
                          "python python-pip" \
                          "python3 python3-pip"
fi

# python3-venv is a separate package on Debian/Ubuntu
if [[ "$PKG_MGR" == "apt" ]] && ! python3 -m venv --help &>/dev/null 2>&1; then
  info "Installing python3-venv…"
  ensure_pkg_index
  sudo apt-get install -y python3-venv
fi

if command -v lsof &>/dev/null; then
  success "lsof found"
else
  install_pkg "lsof" "lsof" "lsof" "lsof" "lsof"
fi

# ── Git ───────────────────────────────────────────────────────────────────────
if command -v git &>/dev/null; then
  success "Git found: $(git --version)"
else
  install_pkg "Git" "git" "git" "git" "git"
fi

# ── Nginx ─────────────────────────────────────────────────────────────────────
if command -v nginx &>/dev/null; then
  success "Nginx found"
else
  install_pkg "Nginx" "nginx" "nginx" "nginx" "nginx"
fi

# ── Python venv & deps ────────────────────────────────────────────────────────
info "Setting up Python virtual environment…"
cd "$SCRIPT_DIR/backend"
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
success "Python dependencies installed"

info "Installing ${CLI_NAME} CLI wrapper…"
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
success "CLI installed — run: ${CLI_NAME} up"

# ── Data dirs ─────────────────────────────────────────────────────────────────
mkdir -p ~/.pdmanager/{apps,logs,certs}
success "Data directories created at ~/.pdmanager/ (legacy compatibility path)"
info "  Tip: place your SSL certificates in ~/.pdmanager/certs/ for easy discovery"

# ── Maintenance pages dir (nginx serves static HTML from here) ────────────────
if command -v nginx &>/dev/null; then
  sudo mkdir -p /var/www/cloudbase/maintenance
  sudo chmod 755 /var/www/cloudbase/maintenance
  success "Maintenance pages directory created at /var/www/cloudbase/maintenance/"
fi

# ── Systemd service ───────────────────────────────────────────────────────────
if command -v systemctl &>/dev/null; then
  echo ""
  USER_NAME="${SUDO_USER:-$(id -un)}"
  SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
  START_SH="$SCRIPT_DIR/start.sh"
  info "Installing systemd service…"
  sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=${APP_NAME}
After=network.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$SCRIPT_DIR
ExecStart=/bin/bash $START_SH up
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
  info "  Manage with: ${CLI_NAME} status"
  info "  Disable boot: ${CLI_NAME} disable"
else
  warn "systemd was not detected. CLI was installed, but boot autostart was skipped."
fi

echo -e "\n${GREEN}${BOLD}Installation complete!${RESET}"
echo -e "\nCLI:         ${BOLD}${CLI_NAME} up${RESET}"
echo -e "Status:      ${BOLD}${CLI_NAME} status${RESET}"
echo -e "Autostart:   ${BOLD}${CLI_NAME} enable${RESET}"
echo -e "Open:        ${BLUE}http://localhost:7823${RESET}\n"
