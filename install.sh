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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "\n${BOLD}Process & Deployment Manager — Installer${RESET}\n"

# ── Python ────────────────────────────────────────────────────────────────────
if command -v python3 &>/dev/null; then
  success "Python found: $(python3 --version)"
else
  echo -e "${RED}[ERR]${RESET}  Python 3 not found. Install: sudo apt install python3 python3-pip python3-venv"
  exit 1
fi

# ── Git ───────────────────────────────────────────────────────────────────────
if command -v git &>/dev/null; then
  success "Git found: $(git --version)"
else
  echo -e "${RED}[ERR]${RESET}  Git not found. Install: sudo apt install git"
  exit 1
fi

# ── Nginx (optional) ──────────────────────────────────────────────────────────
if command -v nginx &>/dev/null; then
  success "Nginx found — domain/SSL features available"
else
  warn "Nginx not installed — domain/SSL features disabled"
  warn "  Install: sudo apt install nginx"
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
mkdir -p ~/.pdmanager/{apps,logs}
success "Data directories created at ~/.pdmanager"

echo -e "\n${GREEN}${BOLD}Installation complete!${RESET}"
echo -e "\nStart with: ${BOLD}./start.sh${RESET}"
echo -e "Open:       ${BLUE}http://localhost:7823${RESET}\n"
