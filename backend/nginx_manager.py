import os
import subprocess


NGINX_SITES_DIR = "/etc/nginx/sites-available"
NGINX_ENABLED_DIR = "/etc/nginx/sites-enabled"


def generate_config(app_name: str, domain: str, port: int, ssl_cert: str = None, ssl_key: str = None) -> str:
    if ssl_cert and ssl_key:
        return f"""server {{
    listen 80;
    server_name {domain};
    return 301 https://$host$request_uri;
}}

server {{
    listen 443 ssl;
    server_name {domain};

    ssl_certificate "{ssl_cert}";
    ssl_certificate_key "{ssl_key}";
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }}
}}
"""
    else:
        return f"""server {{
    listen 80;
    server_name {domain};

    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }}
}}
"""


def _safe_name(app_name: str) -> str:
    """Convert app name to a valid filename (replace spaces/special chars)."""
    import re
    return re.sub(r'[^a-zA-Z0-9_-]', '_', app_name).lower()


def write_nginx_config(app_name: str, config: str) -> tuple[bool, str]:
    safe = _safe_name(app_name)
    config_path = os.path.join(NGINX_SITES_DIR, safe)
    enabled_path = os.path.join(NGINX_ENABLED_DIR, safe)

    try:
        # Write via sudo tee (works without direct write permission)
        result = subprocess.run(
            ["sudo", "tee", config_path],
            input=config, text=True, capture_output=True,
        )
        if result.returncode != 0:
            return False, result.stderr or "Failed to write nginx config"

        # Symlink into sites-enabled
        if not os.path.exists(enabled_path):
            r = subprocess.run(
                ["sudo", "ln", "-sf", config_path, enabled_path],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                return False, r.stderr or "Failed to enable nginx site"

        # Validate config
        result = subprocess.run(["sudo", "nginx", "-t"], capture_output=True, text=True)
        if result.returncode != 0:
            return False, result.stderr

        subprocess.run(["sudo", "systemctl", "reload", "nginx"], capture_output=True)
        return True, "OK"
    except FileNotFoundError:
        return False, "nginx not found — install nginx first (sudo apt install nginx)"
    except Exception as e:
        return False, str(e)


def remove_nginx_config(app_name: str) -> bool:
    safe = _safe_name(app_name)
    config_path = os.path.join(NGINX_SITES_DIR, safe)
    enabled_path = os.path.join(NGINX_ENABLED_DIR, safe)

    removed = False
    for path in [enabled_path, config_path]:
        r = subprocess.run(["sudo", "rm", "-f", path], capture_output=True)
        if r.returncode == 0:
            removed = True

    if removed:
        subprocess.run(["sudo", "systemctl", "reload", "nginx"], capture_output=True)
    return removed
