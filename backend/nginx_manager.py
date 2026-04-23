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

    safe_title   = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_message = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_color   = color if color.startswith("#") and len(color) in (4, 7) else "#f85149"

    if page_type == "downtime":
        return _downtime_template(safe_title, safe_message, safe_color)
    return _update_template(safe_title, safe_message, safe_color)


def _downtime_template(title: str, message: str, color: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;
      background: #070c18;
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 40px 24px;
    }}
    .card {{
      background: #0f172a;
      border: 1px solid #1e2d40;
      border-radius: 20px;
      padding: 52px 56px;
      max-width: 560px;
      width: 100%;
      text-align: center;
      box-shadow: 0 25px 80px rgba(0,0,0,0.65), 0 0 0 1px rgba(255,255,255,0.03);
    }}
    .status-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(248,81,73,0.12);
      border: 1px solid rgba(248,81,73,0.25);
      border-radius: 100px;
      padding: 7px 18px;
      margin-bottom: 36px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: {color};
    }}
    .pulse-dot {{
      width: 7px; height: 7px; border-radius: 50%;
      background: {color};
      animation: pulse 2s ease-in-out infinite;
    }}
    @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.25; }} }}
    h1 {{
      font-size: 30px; font-weight: 700;
      color: #f8fafc; margin-bottom: 16px;
      letter-spacing: -0.025em; line-height: 1.2;
    }}
    .msg {{
      font-size: 15px; color: #64748b;
      line-height: 1.8; margin-bottom: 40px;
    }}
    hr {{ border: none; border-top: 1px solid #1e2d40; margin-bottom: 28px; }}
    .footer {{ font-size: 12px; color: #2d3f55; line-height: 1.6; }}
    .dots {{
      display: flex; gap: 6px;
      justify-content: center; margin-top: 36px;
    }}
    .dots span {{
      width: 6px; height: 6px; border-radius: 50%;
      background: #1e2d40;
      animation: dot 1.4s ease-in-out infinite;
    }}
    .dots span:nth-child(2) {{ animation-delay: 0.2s; }}
    .dots span:nth-child(3) {{ animation-delay: 0.4s; }}
    @keyframes dot {{
      0%, 80%, 100% {{ background: #1e2d40; transform: scale(0.8); }}
      40% {{ background: {color}; transform: scale(1.2); }}
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="status-pill">
      <span class="pulse-dot"></span>
      Service Unavailable
    </div>
    <h1>{title}</h1>
    <p class="msg">{message}</p>
    <hr>
    <div class="footer">
      We're working on restoring the service.<br>This page will reflect the latest status.
    </div>
    <div class="dots">
      <span></span><span></span><span></span>
    </div>
  </div>
</body>
</html>
"""


def _update_template(title: str, message: str, color: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="refresh" content="30">
  <title>{title}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;
      background: #070c18;
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 40px 24px;
    }}
    .card {{
      background: #0f172a;
      border: 1px solid #1e2d40;
      border-radius: 20px;
      padding: 52px 56px;
      max-width: 560px;
      width: 100%;
      text-align: center;
      box-shadow: 0 25px 80px rgba(0,0,0,0.65), 0 0 0 1px rgba(255,255,255,0.03);
    }}
    .rocket {{
      font-size: 56px;
      display: block;
      margin-bottom: 32px;
      animation: float 3.5s ease-in-out infinite;
    }}
    @keyframes float {{
      0%, 100% {{ transform: translateY(0) rotate(-5deg); }}
      50% {{ transform: translateY(-14px) rotate(5deg); }}
    }}
    .status-pill {{
      display: inline-flex;
      align-items: center;
      gap: 9px;
      background: rgba(240,136,62,0.12);
      border: 1px solid rgba(240,136,62,0.25);
      border-radius: 100px;
      padding: 7px 18px;
      margin-bottom: 36px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: {color};
    }}
    .spinner {{
      width: 11px; height: 11px; border-radius: 50%;
      border: 2px solid rgba(240,136,62,0.25);
      border-top-color: {color};
      animation: spin 0.75s linear infinite;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    h1 {{
      font-size: 30px; font-weight: 700;
      color: #f8fafc; margin-bottom: 16px;
      letter-spacing: -0.025em; line-height: 1.2;
    }}
    .msg {{
      font-size: 15px; color: #64748b;
      line-height: 1.8; margin-bottom: 40px;
    }}
    .progress {{
      background: #1e2d40;
      border-radius: 100px;
      height: 3px;
      overflow: hidden;
      margin-bottom: 32px;
    }}
    .progress-bar {{
      height: 100%;
      background: linear-gradient(90deg, transparent, {color}, transparent);
      border-radius: 100px;
      animation: sweep 2s ease-in-out infinite;
    }}
    @keyframes sweep {{
      0%   {{ width: 40%; margin-left: -40%; }}
      100% {{ width: 40%; margin-left: 100%; }}
    }}
    .footer {{ font-size: 12px; color: #2d3f55; }}
  </style>
</head>
<body>
  <div class="card">
    <span class="rocket">🚀</span>
    <div class="status-pill">
      <span class="spinner"></span>
      Deploying Update
    </div>
    <h1>{title}</h1>
    <p class="msg">{message}</p>
    <div class="progress"><div class="progress-bar"></div></div>
    <div class="footer">Page refreshes automatically every 30 seconds.</div>
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
    # NOTE: proxy_intercept_errors must be inside the proxying location block.
    # Named locations cannot use try_files — use rewrite instead.
    server_content = f"""\
    # Auto-serve downtime page when upstream returns 502/503/504
    error_page 502 503 504 @maintenance;
    location @maintenance {{
        root {maint_root};
        rewrite ^ /downtime.html break;
        default_type text/html;
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
        proxy_intercept_errors on;
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

{server_content}
}}
"""
    return f"""server {{
    listen 80;
    server_name {domain};

{server_content}
}}
"""


def _static_page_config(domain: str, maint_root: str, filename: str, ssl_cert: str = None, ssl_key: str = None) -> str:
    # Serve a single static HTML file — works even when both app and PDManager are offline.
    server_content = f"""\
    root {maint_root};

    location / {{
        try_files /{filename} =503;
        default_type text/html;
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

{server_content}
}}
"""
    return f"""server {{
    listen 80;
    server_name {domain};

{server_content}
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
