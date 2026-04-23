import os
import subprocess


NGINX_SITES_DIR = "/etc/nginx/sites-available"
NGINX_ENABLED_DIR = "/etc/nginx/sites-enabled"
MAINTENANCE_DIR = "/var/www/pdmanager/maintenance"


# ── Maintenance page HTML generation ──────────────────────────────────────────

def generate_maintenance_html(
    title: str,
    message: str,
    color: str,
    custom_html: str = None,
    page_type: str = "downtime",
) -> str:
    """Return a full HTML page for downtime or update mode. Uses custom_html if provided."""
    if custom_html:
        return custom_html

    icon_char = "🔧" if page_type == "downtime" else "🚀"
    safe_title   = title.replace("<", "&lt;").replace(">", "&gt;")
    safe_message = message.replace("<", "&lt;").replace(">", "&gt;")
    safe_color   = color if color.startswith("#") and len(color) in (4, 7) else "#f85149"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{safe_title}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0d1117;
      color: #e6edf3;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 24px;
    }}
    .container {{ max-width: 520px; }}
    .icon {{ font-size: 64px; margin-bottom: 28px; animation: pulse 2.5s ease-in-out infinite; }}
    @keyframes pulse {{
      0%, 100% {{ opacity: 1; transform: scale(1); }}
      50%       {{ opacity: 0.65; transform: scale(0.93); }}
    }}
    h1 {{ font-size: 28px; font-weight: 700; color: {safe_color}; margin-bottom: 14px; }}
    p  {{ font-size: 16px; color: #8b949e; line-height: 1.7; }}
    .dots {{ margin-top: 36px; }}
    .dot {{
      display: inline-block; width: 8px; height: 8px;
      background: {safe_color}; border-radius: 50%;
      animation: blink 1.4s ease-in-out infinite;
    }}
    .dot:nth-child(2) {{ animation-delay: 0.2s; margin: 0 7px; }}
    .dot:nth-child(3) {{ animation-delay: 0.4s; }}
    @keyframes blink {{ 0%, 80%, 100% {{ opacity: 0.1; }} 40% {{ opacity: 1; }} }}
  </style>
</head>
<body>
  <div class="container">
    <div class="icon">{icon_char}</div>
    <h1>{safe_title}</h1>
    <p>{safe_message}</p>
    <div class="dots">
      <span class="dot"></span><span class="dot"></span><span class="dot"></span>
    </div>
  </div>
</body>
</html>
"""


def write_maintenance_files(app_id: int, downtime_html: str, update_html: str) -> tuple[bool, str]:
    """Write downtime.html and update.html to /var/www/pdmanager/maintenance/{app_id}/."""
    app_dir = os.path.join(MAINTENANCE_DIR, str(app_id))
    try:
        r = subprocess.run(["sudo", "mkdir", "-p", app_dir], capture_output=True, text=True)
        if r.returncode != 0:
            return False, r.stderr or "Failed to create maintenance directory"

        for filename, content in [("downtime.html", downtime_html), ("update.html", update_html)]:
            path = os.path.join(app_dir, filename)
            r = subprocess.run(["sudo", "tee", path], input=content, text=True, capture_output=True)
            if r.returncode != 0:
                return False, r.stderr or f"Failed to write {filename}"

        subprocess.run(
            ["sudo", "chmod", "644",
             os.path.join(app_dir, "downtime.html"),
             os.path.join(app_dir, "update.html")],
            capture_output=True,
        )
        return True, "OK"
    except FileNotFoundError:
        return False, "sudo not available — cannot write maintenance files"
    except Exception as e:
        return False, str(e)


# ── Nginx config generation ───────────────────────────────────────────────────

def generate_config(
    app_name: str,
    domain: str,
    port: int,
    ssl_cert: str = None,
    ssl_key: str = None,
    app_id: int = None,
    mode: str = "normal",
) -> str:
    """Generate an nginx server block.

    mode:
      'normal'      — proxy to app; 502/503 automatically serve downtime.html
      'maintenance' — serve downtime.html statically (app bypassed)
      'update'      — serve update.html statically (app bypassed)
    """
    maint_root = f"{MAINTENANCE_DIR}/{app_id}" if app_id else f"{MAINTENANCE_DIR}/0"

    if mode == "maintenance":
        return _static_page_config(domain, maint_root, "downtime.html", ssl_cert, ssl_key)
    if mode == "update":
        return _static_page_config(domain, maint_root, "update.html", ssl_cert, ssl_key)
    return _proxy_config(domain, port, maint_root, ssl_cert, ssl_key)


def _proxy_config(domain: str, port: int, maint_root: str, ssl_cert: str = None, ssl_key: str = None) -> str:
    proxy_location = f"""\
    proxy_intercept_errors on;
    error_page 502 503 504 @maintenance;

    location @maintenance {{
        root {maint_root};
        try_files /downtime.html =502;
        internal;
    }}

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
    }}"""

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

{proxy_location}
}}
"""
    return f"""server {{
    listen 80;
    server_name {domain};

{proxy_location}
}}
"""


def _static_page_config(domain: str, maint_root: str, filename: str, ssl_cert: str = None, ssl_key: str = None) -> str:
    location = f"""\
    location / {{
        root {maint_root};
        try_files /{filename} =503;
    }}"""

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

{location}
}}
"""
    return f"""server {{
    listen 80;
    server_name {domain};

{location}
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
