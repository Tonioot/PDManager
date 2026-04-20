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

    ssl_certificate {ssl_cert};
    ssl_certificate_key {ssl_key};
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


def write_nginx_config(app_name: str, config: str) -> tuple[bool, str]:
    config_path = os.path.join(NGINX_SITES_DIR, app_name)
    enabled_path = os.path.join(NGINX_ENABLED_DIR, app_name)

    try:
        with open(config_path, "w") as f:
            f.write(config)

        if not os.path.exists(enabled_path):
            os.symlink(config_path, enabled_path)

        result = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
        if result.returncode != 0:
            return False, result.stderr

        subprocess.run(["systemctl", "reload", "nginx"], capture_output=True)
        return True, "OK"
    except PermissionError:
        return False, "Permission denied — run with sudo or configure sudoers for nginx"
    except FileNotFoundError:
        return False, "nginx not found — install nginx first"
    except Exception as e:
        return False, str(e)


def remove_nginx_config(app_name: str) -> bool:
    config_path = os.path.join(NGINX_SITES_DIR, app_name)
    enabled_path = os.path.join(NGINX_ENABLED_DIR, app_name)

    removed = False
    for path in [enabled_path, config_path]:
        if os.path.exists(path):
            os.remove(path)
            removed = True

    if removed:
        subprocess.run(["systemctl", "reload", "nginx"], capture_output=True)
    return removed
