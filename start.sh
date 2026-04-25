#!/usr/bin/env bash
set -euo pipefail

BOLD='\033[1m'
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
RESET='\033[0m'

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$INSTALL_DIR/backend"
VENV_PATH="$BACKEND_DIR/venv"
PORT=7823
CREDS="$HOME/.cloudbase/credentials"
APP_NAME="Cloudbase"
CLI_NAME="cloudbase"
SERVICE_NAME="cloudbase"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
NGINX_SITE_NAME="cloudbase"
NGINX_CONFIG_PATH="/etc/nginx/sites-available/${NGINX_SITE_NAME}"
NGINX_ENABLED_PATH="/etc/nginx/sites-enabled/${NGINX_SITE_NAME}"
CERTS_DIR="$HOME/.cloudbase/certs"
LOG_DIR="$HOME/.cloudbase/logs"
CLI_LOG_FILE="$LOG_DIR/cloudbase-cli.log"
COMMAND="${1:-start}"

mkdir -p "$CERTS_DIR" "$LOG_DIR"

if [[ $# -gt 0 ]]; then
    shift
fi

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

log_line() {
    local level="$1"
    local color="$2"
    local message="$3"
    printf '[%s] [%s] %s\n' "$(timestamp)" "$level" "$message" >> "$CLI_LOG_FILE"
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
Usage: cloudbase <command> [options]

Core commands:
  start            Start Cloudbase
  stop             Stop Cloudbase
  restart          Restart Cloudbase
  status           Show Cloudbase status
  logs             Show Cloudbase service logs
  enable           Install or refresh systemd autostart and enable it now
  disable          Disable systemd autostart and stop the service
  update           Pull latest changes, reinstall deps and restart

Account commands:
  password         Change the administrator password

Data commands:
  export [file]    Export database + credentials to a .tar.gz archive
  import <file>    Restore database + credentials from a .tar.gz archive

Nginx commands:
  nginx <domain>   Set up nginx reverse proxy for the given domain
  nginx show       Show current nginx config
  nginx disable    Remove nginx config

Certificate commands:
  cert add <source_path> [target_name]
  cert list
  cert path
EOF
}

service_installed() {
    [[ -f "$SERVICE_FILE" ]]
}

require_systemctl() {
    if ! command -v systemctl >/dev/null 2>&1; then
        err "systemctl is not available on this machine"
        exit 1
    fi
}

require_nginx() {
    if ! command -v nginx >/dev/null 2>&1; then
        err "nginx is not installed"
        exit 1
    fi
}

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
            err "Could not detect a supported package manager. Install python3, python3-venv, python3-pip and lsof manually."
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

resolve_cert_path() {
    local input="${1:-}"
    if [[ -z "$input" ]]; then
        echo ""
        return 0
    fi
    if [[ -f "$input" ]]; then
        echo "$input"
        return 0
    fi
    if [[ -f "$CERTS_DIR/$input" ]]; then
        echo "$CERTS_DIR/$input"
        return 0
    fi
    return 1
}

write_service_file() {
    require_systemctl
    local run_user="${SUDO_USER:-$(id -un)}"
    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=${APP_NAME}
After=network.target

[Service]
Type=simple
User=${run_user}
WorkingDirectory=${INSTALL_DIR}
ExecStart=/bin/bash ${INSTALL_DIR}/start.sh run
Restart=on-failure
RestartSec=5
KillMode=none
TimeoutStopSec=15
Delegate=yes

[Install]
WantedBy=multi-user.target
EOF
}

show_status() {
    if service_installed && command -v systemctl >/dev/null 2>&1; then
        systemctl status "$SERVICE_NAME" --no-pager
        return
    fi

    local pid
    pid="$(port_owner_pid)"
    if [[ -n "$pid" ]]; then
        success "Cloudbase is running on port $PORT (pid $pid)"
    else
        warn "Cloudbase is not running"
    fi
}

stop_foreground_instance() {
    local old_pid
    old_pid="$(port_owner_pid)"
    if [[ -z "$old_pid" ]]; then
        warn "No local Cloudbase process is listening on port $PORT"
        return 0
    fi
    info "Stopping process on port $PORT (pid $old_pid)"
    kill -9 "$old_pid" 2>/dev/null || sudo kill -9 "$old_pid" || true
    success "Cloudbase process stopped"
}

show_first_run_password() {
    local pw_file="$HOME/.cloudbase/.first-run-password"
    [[ -f "$pw_file" ]] || return 0
    local pass
    pass=$(cat "$pw_file")
    rm -f "$pw_file"
    printf '\n'
    printf '%b%s%b\n' "$YELLOW" "================================================================" "$RESET"
    printf '%b  FIRST RUN — Administrator password%b\n' "$BOLD" "$RESET"
    printf '%b  Username : admin%b\n' "$BOLD" "$RESET"
    printf '%b  Password : %b%s%b\n' "$BOLD" "$GREEN" "$pass" "$RESET"
    printf '%b  Login at : http://localhost:%s%b\n' "$BOLD" "$PORT" "$RESET"
    printf '%b  Change it via Settings in the UI after login.%b\n' "$BOLD" "$RESET"
    printf '%b%s%b\n' "$YELLOW" "================================================================" "$RESET"
    printf '\n'
}

show_logs() {
    if service_installed && command -v systemctl >/dev/null 2>&1; then
        sudo journalctl -u "$SERVICE_NAME" -n 100 --no-pager
        return
    fi
    if [[ -f "$CLI_LOG_FILE" ]]; then
        tail -n 100 "$CLI_LOG_FILE"
        return
    fi
    warn "No Cloudbase logs found yet"
}

generate_cloudbase_nginx_config() {
    local domain="$1"
    local ssl_cert="${2:-}"
    local ssl_key="${3:-}"

    if [[ -n "$ssl_cert" || -n "$ssl_key" ]]; then
        cat <<EOF
server {
    listen 80;
    server_name ${domain};
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    server_name ${domain};

    ssl_certificate "${ssl_cert}";
    ssl_certificate_key "${ssl_key}";
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
    }
}
EOF
        return
    fi

    cat <<EOF
server {
    listen 80;
    server_name ${domain};

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
    }
}
EOF
}

nginx_setup() {
    require_nginx
    local domain="${1:-}"
    local cert_path=""
    local key_path=""

    if [[ -z "$domain" ]]; then
        err "Usage: cloudbase nginx <domain>"
        exit 1
    fi

    # Auto-detect certificates from the certs directory
    local auto_cert="$CERTS_DIR/fullchain.pem"
    local auto_key="$CERTS_DIR/privkey.pem"
    if [[ -f "$auto_cert" && -f "$auto_key" ]]; then
        cert_path="$auto_cert"
        key_path="$auto_key"
        info "Found SSL certificates in $CERTS_DIR — enabling HTTPS"
    else
        info "No SSL certificates found in $CERTS_DIR — setting up HTTP proxy"
        info "  To enable HTTPS: cloudbase cert add <fullchain.pem> then cloudbase cert add <privkey.pem>"
    fi

    info "Writing nginx config for Cloudbase domain '$domain'"
    generate_cloudbase_nginx_config "$domain" "$cert_path" "$key_path" | sudo tee "$NGINX_CONFIG_PATH" > /dev/null
    sudo ln -sf "$NGINX_CONFIG_PATH" "$NGINX_ENABLED_PATH"
    sudo nginx -t
    sudo systemctl reload nginx

    if [[ -n "$cert_path" ]]; then
        success "Cloudbase is now available at https://$domain"
    else
        success "Cloudbase is now available at http://$domain"
    fi
}

nginx_show() {
    require_nginx
    if sudo test -f "$NGINX_CONFIG_PATH"; then
        sudo cat "$NGINX_CONFIG_PATH"
    else
        warn "No local Cloudbase nginx config exists yet"
    fi
}

nginx_disable() {
    require_nginx
    info "Removing local Cloudbase nginx config"
    sudo rm -f "$NGINX_ENABLED_PATH" "$NGINX_CONFIG_PATH"
    sudo nginx -t
    sudo systemctl reload nginx
    success "Cloudbase nginx config removed"
}

handle_nginx_command() {
    local subcommand="${1:-}"
    shift || true
    case "$subcommand" in
        show)
            nginx_show
            ;;
        disable|remove)
            nginx_disable
            ;;
        "")
            err "Usage: cloudbase nginx <domain>"
            exit 1
            ;;
        *)
            # Treat anything else as a domain name
            nginx_setup "$subcommand" "$@"
            ;;
    esac
}

cert_add() {
    local source_path="${1:-}"
    local target_name="${2:-}"
    if [[ -z "$source_path" ]]; then
        err "Usage: cloudbase cert add <source_path> [target_name]"
        exit 1
    fi
    if [[ ! -f "$source_path" ]]; then
        err "Certificate file not found: $source_path"
        exit 1
    fi
    if [[ -z "$target_name" ]]; then
        target_name="$(basename "$source_path")"
    fi
    cp "$source_path" "$CERTS_DIR/$target_name"
    success "Copied certificate to $CERTS_DIR/$target_name"
}

cert_list() {
    if compgen -G "$CERTS_DIR/*" > /dev/null; then
        ls -1 "$CERTS_DIR"
    else
        warn "No local certificates found in $CERTS_DIR"
    fi
}

handle_cert_command() {
    local subcommand="${1:-}"
    shift || true
    case "$subcommand" in
        add)
            cert_add "$@"
            ;;
        list)
            cert_list
            ;;
        path)
            printf '%s\n' "$CERTS_DIR"
            ;;
        *)
            err "Usage: cloudbase cert <add|list|path>"
            exit 1
            ;;
    esac
}

cmd_password() {
    info "Changing password for the admin account"
    local new_pass
    read -r -s -p "New password: " new_pass
    printf '\n'
    if [[ ${#new_pass} -lt 8 ]]; then
        err "Password must be at least 8 characters"
        exit 1
    fi
    local confirm
    read -r -s -p "Confirm password: " confirm
    printf '\n'
    if [[ "$new_pass" != "$confirm" ]]; then
        err "Passwords do not match"
        exit 1
    fi
    cd "$BACKEND_DIR"
    "$VENV_PATH/bin/python3" - <<PYEOF
import sys, asyncio
sys.path.insert(0, '.')
from database import AsyncSessionLocal, init_db
from models import User
from sqlalchemy import select
import auth

async def run():
    await init_db()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.username == 'admin'))
        user = result.scalars().first()
        if not user:
            print('No admin user found')
            return
        user.hashed_password = auth.hash_password('$new_pass')
        await db.commit()
    print('Password updated')

asyncio.run(run())
PYEOF
    success "Admin password updated"
}

cmd_export() {
    local out="${1:-cloudbase-backup-$(date +%Y%m%d-%H%M%S).tar.gz}"
    local data_dir="$HOME/.cloudbase"
    local tmp_dir
    tmp_dir=$(mktemp -d)
    mkdir -p "$tmp_dir/cloudbase"
    [[ -f "$data_dir/cloudbase.db" ]]  && cp "$data_dir/cloudbase.db"  "$tmp_dir/cloudbase/"
    [[ -f "$data_dir/credentials" ]]   && cp "$data_dir/credentials"   "$tmp_dir/cloudbase/"
    [[ -f "$data_dir/secret_key" ]]    && cp "$data_dir/secret_key"    "$tmp_dir/cloudbase/"
    if [[ -d "$data_dir/certs" ]]; then
        cp -r "$data_dir/certs" "$tmp_dir/cloudbase/"
    fi
    tar -czf "$out" -C "$tmp_dir" cloudbase
    rm -rf "$tmp_dir"
    success "Export saved to $out"
}

cmd_import() {
    local src="${1:-}"
    if [[ -z "$src" || ! -f "$src" ]]; then
        err "Usage: cloudbase import <backup.tar.gz>"
        exit 1
    fi
    local data_dir="$HOME/.cloudbase"
    local tmp_dir
    tmp_dir=$(mktemp -d)
    tar -xzf "$src" -C "$tmp_dir"
    local src_dir="$tmp_dir/cloudbase"
    if [[ ! -d "$src_dir" ]]; then
        err "Invalid backup archive: missing cloudbase/ directory"
        rm -rf "$tmp_dir"
        exit 1
    fi
    mkdir -p "$data_dir"
    [[ -f "$src_dir/cloudbase.db" ]] && cp "$src_dir/cloudbase.db" "$data_dir/" && success "Database restored"
    [[ -f "$src_dir/credentials" ]]  && cp "$src_dir/credentials"  "$data_dir/" && chmod 600 "$data_dir/credentials"
    [[ -f "$src_dir/secret_key" ]]   && cp "$src_dir/secret_key"   "$data_dir/" && chmod 600 "$data_dir/secret_key"
    if [[ -d "$src_dir/certs" ]]; then
        cp -r "$src_dir/certs" "$data_dir/"
        success "Certificates restored"
    fi
    rm -rf "$tmp_dir"
    success "Import complete — restart Cloudbase to apply: cloudbase restart"
}

cmd_update() {
    if ! command -v git >/dev/null 2>&1; then
        err "git is not installed"
        exit 1
    fi
    cd "$INSTALL_DIR"
    info "Stashing any local changes"
    git stash --include-untracked 2>/dev/null || true
    info "Pulling latest changes"
    if ! git pull; then
        err "git pull failed — restoring stash"
        git stash pop 2>/dev/null || true
        exit 1
    fi
    info "Restoring local changes"
    git stash pop 2>/dev/null || true
    info "Reinstalling Python dependencies"
    "$VENV_PATH/bin/pip" install --quiet --upgrade pip
    "$VENV_PATH/bin/pip" install --quiet -r "$BACKEND_DIR/requirements.txt"
    success "Dependencies updated"
    info "Restarting Cloudbase"
    if service_installed && command -v systemctl >/dev/null 2>&1; then
        sudo systemctl restart "$SERVICE_NAME"
        success "Cloudbase updated and restarted"
    else
        stop_foreground_instance
        run_runtime
    fi
}


run_runtime() {
    info "Starting Cloudbase runtime"

    if ! command -v python3 >/dev/null 2>&1 || ! python3 -m venv --help >/dev/null 2>&1 || ! command -v lsof >/dev/null 2>&1; then
        warn "Missing runtime dependencies detected. Installing them now."
        install_missing_runtime_deps "$(detect_pkg_mgr)"
    fi

    mkdir -p "$(dirname "$CREDS")"

    local old_pid
    old_pid="$(port_owner_pid)"
    if [[ -n "$old_pid" ]]; then
        warn "Cleaning up old process on port $PORT (pid $old_pid)"
        kill -9 "$old_pid" 2>/dev/null || sudo kill -9 "$old_pid" || true
    fi

    cd "$BACKEND_DIR"

    if [[ ! -d "$VENV_PATH" || ! -f "$VENV_PATH/bin/pip" ]]; then
        warn "Virtual environment missing or broken. Rebuilding it."
        rm -rf "$VENV_PATH"
        python3 -m venv venv
        success "Virtual environment rebuilt"
    fi

    info "Syncing Python dependencies"
    "$VENV_PATH/bin/pip" install --upgrade pip
    "$VENV_PATH/bin/pip" install -r requirements.txt

    if [[ ! -f "$CREDS" ]]; then
        info "First run detected. Generating administrator password"
        local pass
        pass=$("$VENV_PATH/bin/python3" -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits + '!@#%^&*') for _ in range(20)))")

        "$VENV_PATH/bin/python3" - <<PYEOF
import sys
sys.path.insert(0, '.')
import auth
auth.save_hashed_password(auth.hash_password("$pass"))
PYEOF

        printf '%s' "$pass" > "$HOME/.cloudbase/.first-run-password"
    fi

    success "Launching Cloudbase on port $PORT"
    exec "$VENV_PATH/bin/uvicorn" main:app --host 0.0.0.0 --port "$PORT" --timeout-graceful-shutdown 8
}

printf '\n%b' "$BOLD"
banner
printf '%b\n' "$RESET"
info "Cloudbase CLI log: $CLI_LOG_FILE"

case "$COMMAND" in
    help|-h|--help)
        usage
        exit 0
        ;;
    enable)
        write_service_file
        sudo systemctl daemon-reload
        sudo systemctl enable --now "$SERVICE_NAME"
        success "Cloudbase now starts automatically on boot"
        ;;
    disable)
        require_systemctl
        if service_installed; then
            sudo systemctl disable --now "$SERVICE_NAME"
            success "Cloudbase boot autostart disabled"
        else
            warn "No Cloudbase systemd service is installed"
        fi
        ;;
    status)
        show_status
        ;;
    stop)
        if service_installed && command -v systemctl >/dev/null 2>&1; then
            sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
            success "Cloudbase service stopped"
        fi
        stop_foreground_instance
        ;;
    restart)
        if service_installed && command -v systemctl >/dev/null 2>&1; then
            sudo systemctl restart "$SERVICE_NAME"
            success "Cloudbase service restarted"
        else
            stop_foreground_instance
            run_runtime
        fi
        ;;
    logs)
        show_logs
        ;;
    password)
        cmd_password
        ;;
    export)
        cmd_export "$@"
        ;;
    import)
        cmd_import "$@"
        ;;
    update)
        cmd_update
        ;;
    nginx)
        handle_nginx_command "$@"
        ;;
    cert|certs)
        handle_cert_command "$@"
        ;;
    start)
        show_first_run_password
        if service_installed && command -v systemctl >/dev/null 2>&1; then
            sudo systemctl start "$SERVICE_NAME"
            success "Cloudbase service started"
        else
            run_runtime
        fi
        ;;
    run)
        run_runtime
        ;;
    *)
        err "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac
