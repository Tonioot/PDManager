import logging
import os
import subprocess

log = logging.getLogger("pdm.nginx")

NGINX_SITES_DIR = "/etc/nginx/sites-available"
NGINX_ENABLED_DIR = "/etc/nginx/sites-enabled"
MAINTENANCE_DIR = "/var/www/pdmanager/maintenance"


# â”€â”€ Maintenance page HTML generation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def generate_maintenance_html(
    title: str,
    message: str,
    color: str,
    status_url: str = None,
    custom_html: str = None,
    page_type: str = "downtime",
    logo_data: str = None,
) -> str:
    """Return a full HTML page for downtime or update mode. Uses custom_html if provided."""
    if custom_html:
        return custom_html

    safe_title   = (title or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_message = (message or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_color   = color if color and color.startswith("#") and len(color) in (4, 7) else "#f85149"
    # Validate URL to prevent injection
    import re as _re
    safe_status_url = status_url if status_url and _re.match(r'^https?://', status_url) else None
    # Validate logo: must be a data-URL with an image MIME type
    safe_logo_data = logo_data if logo_data and _re.match(r'^data:image/[a-zA-Z0-9+/.-]+;base64,', logo_data) else None

    if page_type == "downtime":
        return _downtime_template(safe_title, safe_message, safe_color, safe_status_url, safe_logo_data)
    return _update_template(safe_title, safe_message, safe_color, safe_status_url, safe_logo_data)


def _downtime_template(title: str, message: str, color: str, status_url: str = None, logo_data: str = None) -> str:
    status_btn = f"""
    <a class="status-link" href="{status_url}" target="_blank" rel="noopener noreferrer">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="22 12 16 12 13 21 11 3 8 12 2 12"/></svg>
      View status page
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="7" y1="17" x2="17" y2="7"/><polyline points="7 7 17 7 17 17"/></svg>
    </a>""" if status_url else ""
    logo_block = f'<div class="logo"><img src="{logo_data}" alt="Logo" /></div>' if logo_data else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif;
      background: #f1f5f9;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 40px 20px;
    }}
    .card {{
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 20px;
      box-shadow: 0 1px 3px rgba(0,0,0,.04), 0 8px 32px rgba(0,0,0,.07);
      padding: 52px 44px 44px;
      max-width: 460px;
      width: 100%;
      text-align: center;
    }}
    .logo {{ margin-bottom: 28px; }}
    .logo img {{ max-height: 48px; max-width: 180px; object-fit: contain; }}
    .icon-ring {{
      width: 72px; height: 72px;
      border-radius: 50%;
      background: color-mix(in srgb, {color} 8%, #fff);
      border: 1.5px solid color-mix(in srgb, {color} 20%, transparent);
      display: flex; align-items: center; justify-content: center;
      margin: 0 auto 24px;
      position: relative;
    }}
    .icon-ring::before {{
      content: '';
      position: absolute; inset: -5px; border-radius: 50%;
      border: 2px solid color-mix(in srgb, {color} 15%, transparent);
      border-top-color: {color};
      animation: spin 2.5s linear infinite;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    .badge {{
      display: inline-flex; align-items: center; gap: 7px;
      background: color-mix(in srgb, {color} 8%, #fff);
      border: 1px solid color-mix(in srgb, {color} 22%, transparent);
      border-radius: 100px; padding: 5px 14px; margin-bottom: 22px;
      font-size: 10.5px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
      color: {color};
    }}
    .dot {{ width: 6px; height: 6px; border-radius: 50%; background: {color}; animation: blink 1.8s ease-in-out infinite; }}
    @keyframes blink {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: .25; }} }}
    h1 {{ font-size: 26px; font-weight: 700; color: #0f172a; letter-spacing: -.03em; line-height: 1.25; margin-bottom: 12px; }}
    .msg {{ font-size: 15px; color: #64748b; line-height: 1.8; margin-bottom: 28px; }}
    .divider {{ width: 40px; height: 2px; background: linear-gradient(90deg, transparent, {color}, transparent); margin: 0 auto 24px; border-radius: 2px; }}
    .status-link {{
      display: inline-flex; align-items: center; gap: 7px;
      font-size: 13px; font-weight: 500; color: {color};
      text-decoration: none; padding: 9px 20px;
      border: 1px solid color-mix(in srgb, {color} 30%, transparent);
      border-radius: 10px;
      background: color-mix(in srgb, {color} 5%, transparent);
      transition: background .15s;
    }}
    .status-link:hover {{ background: color-mix(in srgb, {color} 12%, transparent); }}
    .footer {{ margin-top: 36px; font-size: 11px; color: #94a3b8; }}
  </style>
</head>
<body>
  <div class="card">
    {logo_block}
    <div class="icon-ring">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round">
        <circle cx="12" cy="12" r="10"/>
        <polyline points="12 6 12 12 16 14"/>
      </svg>
    </div>
    <div class="badge"><span class="dot"></span>Service Unavailable</div>
    <h1>{title}</h1>
    <p class="msg">{message}</p>
    <div class="divider"></div>
    {status_btn}
    <div class="footer">We&rsquo;re working on it &mdash; this page updates automatically.</div>
  </div>
</body>
</html>
"""


def _update_template(title: str, message: str, color: str, status_url: str = None, logo_data: str = None) -> str:
    status_btn = f"""
    <a class="status-link" href="{status_url}" target="_blank" rel="noopener noreferrer">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="22 12 16 12 13 21 11 3 8 12 2 12"/></svg>
      View status page
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="7" y1="17" x2="17" y2="7"/><polyline points="7 7 17 7 17 17"/></svg>
    </a>""" if status_url else ""
    logo_block = f'<div class="logo"><img src="{logo_data}" alt="Logo" /></div>' if logo_data else ""

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
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif;
      background: #f1f5f9;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 40px 20px;
    }}
    .card {{
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 20px;
      box-shadow: 0 1px 3px rgba(0,0,0,.04), 0 8px 32px rgba(0,0,0,.07);
      padding: 52px 44px 44px;
      max-width: 460px;
      width: 100%;
      text-align: center;
    }}
    .logo {{ margin-bottom: 28px; }}
    .logo img {{ max-height: 48px; max-width: 180px; object-fit: contain; }}
    .icon-wrap {{
      width: 72px; height: 72px;
      border-radius: 20px;
      background: color-mix(in srgb, {color} 8%, #fff);
      border: 1.5px solid color-mix(in srgb, {color} 22%, transparent);
      display: flex; align-items: center; justify-content: center;
      margin: 0 auto 24px;
    }}
    .badge {{
      display: inline-flex; align-items: center; gap: 8px;
      background: color-mix(in srgb, {color} 8%, #fff);
      border: 1px solid color-mix(in srgb, {color} 22%, transparent);
      border-radius: 100px; padding: 5px 14px; margin-bottom: 22px;
      font-size: 10.5px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
      color: {color};
    }}
    .spinner {{
      width: 10px; height: 10px; border-radius: 50%;
      border: 2px solid color-mix(in srgb, {color} 22%, transparent);
      border-top-color: {color};
      animation: spin .8s linear infinite;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    h1 {{ font-size: 26px; font-weight: 700; color: #0f172a; letter-spacing: -.03em; line-height: 1.25; margin-bottom: 12px; }}
    .msg {{ font-size: 15px; color: #64748b; line-height: 1.8; margin-bottom: 28px; }}
    .track {{ background: #f1f5f9; border-radius: 100px; height: 3px; overflow: hidden; margin-bottom: 28px; }}
    .bar {{ height: 100%; background: linear-gradient(90deg, transparent, {color}, transparent); animation: sweep 2.2s ease-in-out infinite; }}
    @keyframes sweep {{ 0% {{ transform: translateX(-100%) scaleX(.5); }} 100% {{ transform: translateX(200%) scaleX(.5); }} }}
    .status-link {{
      display: inline-flex; align-items: center; gap: 7px;
      font-size: 13px; font-weight: 500; color: {color};
      text-decoration: none; padding: 9px 20px;
      border: 1px solid color-mix(in srgb, {color} 30%, transparent);
      border-radius: 10px;
      background: color-mix(in srgb, {color} 5%, transparent);
      transition: background .15s;
    }}
    .status-link:hover {{ background: color-mix(in srgb, {color} 12%, transparent); }}
    .footer {{ margin-top: 28px; font-size: 11px; color: #94a3b8; }}
  </style>
</head>
<body>
  <div class="card">
    {logo_block}
    <div class="icon-wrap">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="16 16 12 12 8 16"/>
        <line x1="12" y1="12" x2="12" y2="21"/>
        <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
      </svg>
    </div>
    <div class="badge"><span class="spinner"></span>Deploying Update</div>
    <h1>{title}</h1>
    <p class="msg">{message}</p>
    <div class="track"><div class="bar"></div></div>
    {status_btn}
    <div class="footer">Page auto-refreshes every 30 seconds.</div>
  </div>
</body>
</html>
"""



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
        log.info("[maint-files] done â€” files: %s", os.listdir(app_dir) if os.path.isdir(app_dir) else "DIR MISSING")
        return True, "OK"
    except FileNotFoundError:
        log.error("[maint-files] sudo not found")
        return False, "sudo not available â€” cannot write maintenance files"
    except Exception as e:
        log.exception("[maint-files] unexpected error")
        return False, str(e)


# â”€â”€ Nginx config generation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
      'normal'      â€” proxy to app; 502/503 automatically serve downtime.html
      'maintenance' â€” serve downtime.html statically (app bypassed)
      'update'      â€” serve update.html statically (app bypassed)
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
    # Serve a single static HTML file â€” works even when both app and PDManager are offline.
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
        return True, "OK"
    except Exception as exc:
        log.exception("[maint-files] unexpected error: %s", exc)
        return False, str(exc)


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
        return False, "nginx not found â€” install nginx first (sudo apt install nginx)"
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
