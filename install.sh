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

echo -e "\n${BOLD}Process & Deployment Manager — Installer${RESET}\n"

# ── Detect package manager ────────────────────────────────────────────────────
PKG_MGR=""
if   command -v apt-get &>/dev/null; then PKG_MGR="apt"
elif command -v dnf     &>/dev/null; then PKG_MGR="dnf"
elif command -v yum     &>/dev/null; then PKG_MGR="yum"
elif command -v pacman  &>/dev/null; then PKG_MGR="pacman"
elif command -v zypper  &>/dev/null; then PKG_MGR="zypper"
fi

install_pkg() {
  # usage: install_pkg <display-name> <apt-pkg> <dnf-pkg> <pacman-pkg> <zypper-pkg>
  local name="$1" apt_pkg="$2" dnf_pkg="$3" pac_pkg="$4" zy_pkg="$5"
  info "Installing $name…"
  case "$PKG_MGR" in
    apt)    sudo apt-get install -y "$apt_pkg" ;;
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
  sudo apt-get install -y python3-venv
fi

# ── Git ───────────────────────────────────────────────────────────────────────
if command -v git &>/dev/null; then
  success "Git found: $(git --version)"
else
  install_pkg "Git" "git" "git" "git" "git"
fi

# ── Nginx (optional) ──────────────────────────────────────────────────────────
if command -v nginx &>/dev/null; then
  success "Nginx found — domain/SSL features available"
else
  warn "Nginx not installed — domain/SSL features will be disabled."
  read -rp "  Install Nginx now? [y/N] " ans
  if [[ "$ans" =~ ^[Yy]$ ]]; then
    install_pkg "Nginx" "nginx" "nginx" "nginx" "nginx"
  else
    warn "Skipping Nginx — you can install it later with your package manager"
  fi
fi

# ── Python venv & deps ────────────────────────────────────────────────────────
info "Setting up Python virtual environment…"
cd "$SCRIPT_DIR/backend"
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
success "Python dependencies installed"

# ── Data dirs ─────────────────────────────────────────────────────────────────
mkdir -p ~/.pdmanager/{apps,logs,certs}
success "Data directories created at ~/.pdmanager/"
info "  Tip: place your SSL certificates in ~/.pdmanager/certs/ for easy discovery"

# ── Systemd service (optional) ────────────────────────────────────────────────
if command -v systemctl &>/dev/null && [[ "$EUID" -ne 0 ]]; then
  echo ""
  read -rp "Install PDManager as a systemd service (auto-start on boot)? [y/N] " svc
  if [[ "$svc" =~ ^[Yy]$ ]]; then
    USER_NAME="$(id -un)"
    SERVICE_FILE="/etc/systemd/system/pdmanager.service"
    START_SH="$SCRIPT_DIR/start.sh"
    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Process & Deployment Manager
After=network.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$SCRIPT_DIR
ExecStart=/bin/bash $START_SH
Restart=on-failure
RestartSec=5
KillMode=none
TimeoutStopSec=15
Delegate=yes

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable pdmanager.service
    success "Systemd service installed and enabled (pdmanager.service)"
    info "  Start now: sudo systemctl start pdmanager"
    info "  Status:    sudo systemctl status pdmanager"
  fi
fi

# ── Shell alias (optional) ────────────────────────────────────────────────────
ALIAS_LINE="alias pdmanager='bash $SCRIPT_DIR/start.sh'"
if ! grep -qF "pdmanager" ~/.bashrc 2>/dev/null; then
  read -rp "Add 'pdmanager' alias to ~/.bashrc? [y/N] " alias_ans
  if [[ "$alias_ans" =~ ^[Yy]$ ]]; then
    echo "" >> ~/.bashrc
    echo "# Process & Deployment Manager" >> ~/.bashrc
    echo "$ALIAS_LINE" >> ~/.bashrc
    success "Alias added — run 'source ~/.bashrc' or open a new terminal"
  fi
fi

echo -e "\n${GREEN}${BOLD}Installation complete!${RESET}"
echo -e "\nStart with:  ${BOLD}./start.sh${RESET}"
echo -e "Open:        ${BLUE}http://localhost:7823${RESET}\n"
