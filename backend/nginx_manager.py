import logging
import os
import subprocess

log = logging.getLogger("pdm.nginx")

NGINX_SITES_DIR = "/etc/nginx/sites-available"
NGINX_ENABLED_DIR = "/etc/nginx/sites-enabled"
MAINTENANCE_DIR = "/var/www/pdmanager/maintenance"


# ── Maintenance page HTML generation ──────────────────────────────────────────

def generate_maintenance_html(
    title: str,
    message: str,
    color: str,
    status_url: str = None,
    custom_html: str = None,
    page_type: str = "downtime",
) -> str:
    """Return a full HTML page for downtime or update mode. Uses custom_html if provided."""
    if custom_html:
        return custom_html

    safe_title   = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_message = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_color   = color if color.startswith("#") and len(color) in (4, 7) else "#f85149"
    # Validate URL to prevent injection
    import re as _re
    safe_status_url = status_url if status_url and _re.match(r'^https?://', status_url) else None

    if page_type == "downtime":
        return _downtime_template(safe_title, safe_message, safe_color, safe_status_url)
    return _update_template(safe_title, safe_message, safe_color, safe_status_url)


def _downtime_template(title: str, message: str, color: str, status_url: str = None) -> str:
    status_btn = f"""
    <a class="status-link" href="{status_url}" target="_blank" rel="noopener noreferrer">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 8 12 12 14 14"/></svg>
      View status page
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="7" y1="17" x2="17" y2="7"/><polyline points="7 7 17 7 17 17"/></svg>
    </a>""" if status_url else ""

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
      background: #060a12;
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 40px 24px;
    }}
    .wrap {{
      max-width: 480px;
      width: 100%;
      text-align: center;
    }}
    .logo-ring {{
      width: 72px; height: 72px;
      border-radius: 50%;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.07);
      display: flex; align-items: center; justify-content: center;
      margin: 0 auto 28px;
      position: relative;
    }}
    .logo-ring::before {{
      content: '';
      position: absolute;
      inset: -4px;
      border-radius: 50%;
      border: 2px solid transparent;
      border-top-color: {color};
      animation: spin 2.5s linear infinite;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    .logo-ring svg {{ opacity: 0.7; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      background: color-mix(in srgb, {color} 12%, transparent);
      border: 1px solid color-mix(in srgb, {color} 28%, transparent);
      border-radius: 100px;
      padding: 5px 14px;
      margin-bottom: 24px;
      font-size: 10.5px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: {color};
    }}
    .dot {{
      width: 6px; height: 6px; border-radius: 50%;
      background: {color};
      animation: blink 1.8s ease-in-out infinite;
    }}
    @keyframes blink {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.2; }} }}
    h1 {{
      font-size: 28px; font-weight: 700;
      color: #f1f5f9;
      letter-spacing: -0.03em; line-height: 1.2;
      margin-bottom: 12px;
    }}
    .msg {{
      font-size: 15px;
      color: #64748b;
      line-height: 1.75;
      margin-bottom: 32px;
    }}
    .divider {{
      width: 48px; height: 2px;
      background: linear-gradient(90deg, transparent, {color}, transparent);
      border-radius: 2px;
      margin: 0 auto 28px;
    }}
    .status-link {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12.5px;
      font-weight: 500;
      color: {color};
      text-decoration: none;
      opacity: 0.75;
      transition: opacity 0.15s;
    }}
    .status-link:hover {{ opacity: 1; }}
    .footer {{
      margin-top: 48px;
      font-size: 11px;
      color: #1e293b;
      letter-spacing: 0.02em;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="logo-ring">
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
    </div>
    <div class="badge">
      <span class="dot"></span>
      Service Unavailable
    </div>
    <h1>{title}</h1>
    <p class="msg">{message}</p>
    <div class="divider"></div>
    {status_btn}
    <div class="footer">We&rsquo;re working on it &mdash; this page updates automatically.</div>
  </div>
</body>
</html>
"""


def _update_template(title: str, message: str, color: str, status_url: str = None) -> str:
    status_btn = f"""
    <a class="status-link" href="{status_url}" target="_blank" rel="noopener noreferrer">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 8 12 12 14 14"/></svg>
      View status page
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="7" y1="17" x2="17" y2="7"/><polyline points="7 7 17 7 17 17"/></svg>
    </a>""" if status_url else ""

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
      background: #060a12;
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 40px 24px;
    }}
    .wrap {{
      max-width: 480px;
      width: 100%;
      text-align: center;
    }}
    .icon-wrap {{
      width: 72px; height: 72px;
      border-radius: 20px;
      background: color-mix(in srgb, {color} 10%, transparent);
      border: 1px solid color-mix(in srgb, {color} 22%, transparent);
      display: flex; align-items: center; justify-content: center;
      margin: 0 auto 28px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: color-mix(in srgb, {color} 10%, transparent);
      border: 1px solid color-mix(in srgb, {color} 25%, transparent);
      border-radius: 100px;
      padding: 5px 14px;
      margin-bottom: 24px;
      font-size: 10.5px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: {color};
    }}
    .spinner {{
      width: 10px; height: 10px; border-radius: 50%;
      border: 2px solid color-mix(in srgb, {color} 25%, transparent);
      border-top-color: {color};
      animation: spin 0.7s linear infinite;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    h1 {{
      font-size: 28px; font-weight: 700;
      color: #f1f5f9;
      letter-spacing: -0.03em; line-height: 1.2;
      margin-bottom: 12px;
    }}
    .msg {{
      font-size: 15px;
      color: #64748b;
      line-height: 1.75;
      margin-bottom: 32px;
    }}
    .track {{
      background: rgba(255,255,255,0.05);
      border-radius: 100px;
      height: 2px;
      overflow: hidden;
      margin-bottom: 32px;
    }}
    .bar {{
      height: 100%;
      background: linear-gradient(90deg, transparent, {color}, transparent);
      animation: sweep 2.2s ease-in-out infinite;
    }}
    @keyframes sweep {{
      0%   {{ transform: translateX(-100%) scaleX(0.5); }}
      100% {{ transform: translateX(200%) scaleX(0.5); }}
    }}
    .status-link {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12.5px;
      font-weight: 500;
      color: {color};
      text-decoration: none;
      opacity: 0.75;
      transition: opacity 0.15s;
    }}
    .status-link:hover {{ opacity: 1; }}
    .footer {{
      margin-top: 48px;
      font-size: 11px;
      color: #1e293b;
      letter-spacing: 0.02em;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="icon-wrap">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/><polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/></svg>
    </div>
    <div class="badge">
      <span class="spinner"></span>
      Deploying Update
    </div>
    <h1>{title}</h1>
    <p class="msg">{message}</p>
    <div class="track"><div class="bar"></div></div>
    {status_btn}
    <div class="footer">Page auto-refreshes every 30 seconds.</div>
  </div>
</body>
</html>
"""


def write_maintenance_files(app_id: int, downtime_html: str, update_html: str) -> tuple[bool, str]:
    """Write downtime.html and update.html to /var/www/pdmanager/maintenance/{app_id}/."""
    app_dir = os.path.join(MAINTENANCE_DIR, str(app_id))
    log.info("[maint-files] writing to %s", app_dir)
    try:
        r = subprocess.run(["sudo", "mkdir", "-p", app_dir], capture_output=True, text=True)
        log.info("[maint-files] mkdir rc=%d stderr=%r", r.returncode, r.stderr)
        if r.returncode != 0:
            return False, r.stderr or "Failed to create maintenance directory"

        for filename, content in [("downtime.html", downtime_html), ("update.html", update_html)]:
            path = os.path.join(app_dir, filename)
            r = subprocess.run(["sudo", "tee", path], input=content, text=True, capture_output=True)
            log.info("[maint-files] tee %s rc=%d stderr=%r", path, r.returncode, r.stderr)
            if r.returncode != 0:
                return False, r.stderr or f"Failed to write {filename}"

        r = subprocess.run(
            ["sudo", "chmod", "644",
             os.path.join(app_dir, "downtime.html"),
             os.path.join(app_dir, "update.html")],
            capture_output=True, text=True,
        )
        log.info("[maint-files] chmod rc=%d stderr=%r", r.returncode, r.stderr)
        log.info("[maint-files] done — files: %s", os.listdir(app_dir) if os.path.isdir(app_dir) else "DIR MISSING")
        return True, "OK"
    except FileNotFoundError:
        log.error("[maint-files] sudo not found")
        return False, "sudo not available — cannot write maintenance files"
    except Exception as e:
        log.exception("[maint-files] unexpected error")
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
    # We use a regular 'internal' location (not named @) so that try_files works.
    # Named locations don't support try_files, which caused the file to not be served.
    server_content = f"""\
    # Auto-serve downtime page when upstream returns 502/503/504.
    # =200 overrides the status so Cloudflare (and other proxies) don't intercept it.
    error_page 502 503 504 =200 /_pdm_maintenance;
    location = /_pdm_maintenance {{
        internal;
        root {maint_root};
        try_files /downtime.html =200;
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
        # =200 fallback: never let Cloudflare intercept with its own error page
        try_files /{filename} =200;
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
    log.info("[nginx-cfg] writing config for app=%r safe=%r path=%s", app_name, safe, config_path)
    log.debug("[nginx-cfg] config content:\n%s", config)

    try:
        # Write via sudo tee (works without direct write permission)
        result = subprocess.run(
            ["sudo", "tee", config_path],
            input=config, text=True, capture_output=True,
        )
        log.info("[nginx-cfg] tee config rc=%d stderr=%r", result.returncode, result.stderr)
        if result.returncode != 0:
            return False, result.stderr or "Failed to write nginx config"

        # Symlink into sites-enabled
        if not os.path.exists(enabled_path):
            r = subprocess.run(
                ["sudo", "ln", "-sf", config_path, enabled_path],
                capture_output=True, text=True,
            )
            log.info("[nginx-cfg] symlink rc=%d stderr=%r", r.returncode, r.stderr)
            if r.returncode != 0:
                return False, r.stderr or "Failed to enable nginx site"
        else:
            log.info("[nginx-cfg] symlink already exists at %s", enabled_path)
            # Always re-create symlink to ensure it points to current config
            subprocess.run(["sudo", "ln", "-sf", config_path, enabled_path], capture_output=True)

        # Validate config
        result = subprocess.run(["sudo", "nginx", "-t"], capture_output=True, text=True)
        log.info("[nginx-cfg] nginx -t rc=%d stdout=%r stderr=%r", result.returncode, result.stdout, result.stderr)
        if result.returncode != 0:
            return False, result.stderr

        r = subprocess.run(["sudo", "systemctl", "reload", "nginx"], capture_output=True, text=True)
        log.info("[nginx-cfg] reload rc=%d stderr=%r", r.returncode, r.stderr)
        return True, "OK"
    except FileNotFoundError:
        log.error("[nginx-cfg] nginx not found")
        return False, "nginx not found — install nginx first (sudo apt install nginx)"
    except Exception as e:
        log.exception("[nginx-cfg] unexpected error")
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
