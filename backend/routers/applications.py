import asyncio
import json
import os
import shutil
import subprocess
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Application
import process_manager as pm
import nginx_manager as nm
import token_vault

router = APIRouter(prefix="/api/apps", tags=["applications"])


class DeployRequest(BaseModel):
    name: str
    repo_url: str
    github_token: Optional[str] = None
    github_token_id: Optional[str] = None   # ID of a saved vault token
    domain: Optional[str] = None
    ssl_cert_path: Optional[str] = None
    ssl_key_path: Optional[str] = None
    start_command: Optional[str] = None
    port: Optional[int] = None
    env_vars: Optional[dict] = None


class UpdateRequest(BaseModel):
    domain: Optional[str] = None
    ssl_cert_path: Optional[str] = None
    ssl_key_path: Optional[str] = None
    start_command: Optional[str] = None
    port: Optional[int] = None
    env_vars: Optional[dict] = None
    github_token: Optional[str] = None
    github_token_id: Optional[str] = None   # ID of a saved vault token
    auto_start:     Optional[bool] = None
    restart_policy: Optional[str] = None   # no | always | on-failure


class MaintenancePageConfig(BaseModel):
    title: str = ""
    message: str = ""
    color: str = "#f85149"
    custom_html: Optional[str] = None


class MaintenanceSettings(BaseModel):
    downtime_page: MaintenancePageConfig = MaintenancePageConfig()
    update_page: MaintenancePageConfig = MaintenancePageConfig(color="#f0883e")


def _get_nginx_mode(app: Application) -> str:
    if app.update_mode:
        return "update"
    if app.maintenance_mode:
        return "maintenance"
    return "normal"


def _ensure_maintenance_files(app: Application, app_id: int) -> None:
    """Write maintenance HTML files from stored config (or defaults)."""
    downtime_cfg = json.loads(app.downtime_page or "{}")
    update_cfg   = json.loads(app.update_page   or "{}")

    downtime_html = nm.generate_maintenance_html(
        downtime_cfg.get("title")       or "Down for Maintenance",
        downtime_cfg.get("message")     or "We'll be back shortly.",
        downtime_cfg.get("color")       or "#f85149",
        downtime_cfg.get("custom_html"),
        "downtime",
    )
    update_html = nm.generate_maintenance_html(
        update_cfg.get("title")         or "Updating\u2026",
        update_cfg.get("message")       or "We\u2019re deploying a new version. Check back soon.",
        update_cfg.get("color")         or "#f0883e",
        update_cfg.get("custom_html"),
        "update",
    )
    nm.write_maintenance_files(app_id, downtime_html, update_html)


def _resolve_token(req_token: Optional[str], req_token_id: Optional[str]) -> Optional[str]:
    """Return raw token: prefer vault lookup, fall back to inline value."""
    if req_token_id:
        resolved = token_vault.resolve(req_token_id)
        if resolved:
            return resolved
    return req_token or None


def _build_clone_url(repo_url: str, token: Optional[str]) -> str:
    if token and "github.com" in repo_url:
        repo_url = repo_url.replace("https://", f"https://{token}@")
    return repo_url


def _run_install(app_dir: str) -> None:
    if os.path.exists(os.path.join(app_dir, "package.json")):
        subprocess.run(["npm", "install"], cwd=app_dir, capture_output=True, text=True)

    if os.path.exists(os.path.join(app_dir, "requirements.txt")):
        subprocess.run(
            ["pip", "install", "-r", "requirements.txt"],
            cwd=app_dir, capture_output=True, text=True,
        )

    if os.path.exists(os.path.join(app_dir, "Gemfile")):
        subprocess.run(["bundle", "install"], cwd=app_dir, capture_output=True, text=True)

    if os.path.exists(os.path.join(app_dir, "composer.json")):
        subprocess.run(["composer", "install"], cwd=app_dir, capture_output=True, text=True)

    if os.path.exists(os.path.join(app_dir, "go.mod")):
        subprocess.run(["go", "mod", "download"], cwd=app_dir, capture_output=True, text=True)


async def _deploy_app(app: Application):
    app_dir = pm.get_app_dir(app.name)
    os.makedirs(app_dir, exist_ok=True)

    clone_url = _build_clone_url(app.repo_url, app.github_token)
    result = subprocess.run(
        ["git", "clone", clone_url, "."],
        cwd=app_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Git clone failed: {result.stderr}")

    app.working_dir = app_dir
    app_type, default_cmd, default_port = pm.detect_app_type(app_dir)

    if not app.start_command:
        app.start_command = default_cmd
    if not app.port and default_port:
        app.port = default_port

    app.app_type = pm.detect_app_type_from_command(app.start_command) if app.start_command else app_type

    await asyncio.to_thread(_run_install, app_dir)


@router.get("/system/certs")
async def discover_certs():
    """Scan common certificate and key locations on this machine."""
    import glob

    cert_patterns = [
        "/etc/letsencrypt/live/*/fullchain.pem",
        "/etc/letsencrypt/live/*/cert.pem",
        "/etc/ssl/certs/*.pem",
        "/etc/ssl/certs/*.crt",
        "/etc/nginx/ssl/*.pem",
        "/etc/nginx/ssl/*.crt",
        "/etc/nginx/certs/*.pem",
        "/etc/nginx/certs/*.crt",
        os.path.expanduser("~/.pdmanager/certs/*.pem"),
        os.path.expanduser("~/.pdmanager/certs/*.crt"),
    ]
    key_patterns = [
        "/etc/letsencrypt/live/*/privkey.pem",
        "/etc/ssl/private/*.pem",
        "/etc/ssl/private/*.key",
        "/etc/nginx/ssl/*.key",
        "/etc/nginx/certs/*.key",
        os.path.expanduser("~/.pdmanager/certs/*.key"),
        os.path.expanduser("~/.pdmanager/certs/*.pem"),
    ]

    certs: list[str] = []
    keys: list[str] = []

    for pattern in cert_patterns:
        try:
            certs.extend(glob.glob(pattern))
        except Exception:
            pass
    for pattern in key_patterns:
        try:
            keys.extend(glob.glob(pattern))
        except Exception:
            pass

    return {"certs": sorted(set(certs)), "keys": sorted(set(keys))}


@router.get("/{app_id}/certs")
async def discover_app_certs(app_id: int, db: AsyncSession = Depends(get_db)):
    """Scan for cert/key files inside the app's working directory only."""
    import glob

    app = await _get_or_404(app_id, db)
    base = app.working_dir
    if not base or not os.path.isdir(base):
        return {"certs": [], "keys": []}

    cert_exts = ("*.pem", "*.crt", "*.cer")
    key_exts  = ("*.pem", "*.key")

    certs: list[str] = []
    keys:  list[str] = []

    for ext in cert_exts:
        certs.extend(glob.glob(os.path.join(base, "**", ext), recursive=True))
    for ext in key_exts:
        keys.extend(glob.glob(os.path.join(base, "**", ext), recursive=True))

    # Heuristic: files with 'key' in name are more likely private keys
    key_set  = sorted({p for p in set(keys)  if "key" in os.path.basename(p).lower() or p.endswith(".key")})
    cert_set = sorted({p for p in set(certs) if "key" not in os.path.basename(p).lower()})
    # Fallback: if no dedicated key files found, show all .pem
    if not key_set:
        key_set = sorted(set(keys))

    return {"certs": cert_set, "keys": key_set}


@router.post("/{app_id}/certs/upload")
async def upload_app_cert(app_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """Upload a cert/key file into the app's certs subfolder and return its path."""
    app = await _get_or_404(app_id, db)
    allowed_exts = {".pem", ".crt", ".cer", ".key"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(400, "Only .pem, .crt, .cer, .key files are allowed")
    safe_name = os.path.basename(file.filename).replace("..", "").lstrip("/")
    base = app.working_dir or os.path.expanduser(f"~/.pdmanager/certs/{app.name}")
    dest_dir = os.path.join(base, "certs")
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, safe_name)
    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)
    return {"path": dest_path}


@router.get("/system/service-file")
async def get_service_file():
    """Return a systemd unit file for auto-starting PDManager on boot."""
    import getpass
    script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "start.sh"))
    user = getpass.getuser()
    content = f"""[Unit]
Description=Process & Deployment Manager
After=network.target

[Service]
Type=simple
User={user}
ExecStart=/bin/bash {script_dir}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    return {
        "content": content,
        "path": "/etc/systemd/system/pdmanager.service",
    }


async def _sync_process_status(app, db) -> None:
    """Reconcile DB status with actual OS state. Uses port recovery as fallback."""
    if not app.pid:
        return
    alive = await asyncio.to_thread(pm.is_process_running, app.pid, app.id)
    if alive:
        app.status = "running"
        return
    # Stored PID is dead — try to recover via port before declaring stopped
    if app.port:
        recovered = await asyncio.to_thread(pm.find_process_by_port, app.port)
        if recovered:
            app.pid = recovered
            app.status = "running"
            await db.commit()
            return
    app.status = "stopped"
    app.pid = None
    await db.commit()


@router.get("")
async def list_apps(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Application))
    apps = result.scalars().all()

    # Check all process statuses in parallel (each check runs blocking psutil calls in threads)
    async def _check(app):
        if not app.pid:
            return app.id, app.status, app.pid
        alive = await asyncio.to_thread(pm.is_process_running, app.pid, app.id)
        if alive:
            return app.id, "running", app.pid
        if app.port:
            recovered = await asyncio.to_thread(pm.find_process_by_port, app.port)
            if recovered:
                return app.id, "running", recovered
        return app.id, "stopped", None

    checks = await asyncio.gather(*[_check(a) for a in apps])

    id_map = {a.id: a for a in apps}
    dirty = False
    for app_id, new_status, new_pid in checks:
        a = id_map[app_id]
        if a.status != new_status or a.pid != new_pid:
            a.status = new_status
            a.pid = new_pid
            dirty = True
    if dirty:
        await db.commit()

    return [_app_to_dict(a) for a in apps]


@router.post("")
async def deploy_app(req: DeployRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Application).where(Application.name == req.name))
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"App '{req.name}' already exists")

    app = Application(
        name=req.name,
        repo_url=req.repo_url,
        github_token=_resolve_token(req.github_token, req.github_token_id),
        domain=req.domain,
        ssl_cert_path=req.ssl_cert_path,
        ssl_key_path=req.ssl_key_path,
        start_command=req.start_command,
        port=req.port,
        env_vars=json.dumps(req.env_vars or {}),
        status="deploying",
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)

    try:
        await _deploy_app(app)
        app.status = "stopped"

        if app.domain and app.port:
            config = nm.generate_config(
                app.name, app.domain, app.port,
                app.ssl_cert_path, app.ssl_key_path,
                app_id=app.id, mode=_get_nginx_mode(app),
            )
            ok, msg = nm.write_nginx_config(app.name, config)
            app.nginx_enabled = ok
            if ok:
                _ensure_maintenance_files(app, app.id)

        await db.commit()
        await db.refresh(app)
        return _app_to_dict(app)
    except Exception as e:
        app.status = "error"
        await db.commit()
        raise HTTPException(500, str(e))


@router.get("/{app_id}")
async def get_app(app_id: int, db: AsyncSession = Depends(get_db)):
    app = await _get_or_404(app_id, db)
    await _sync_process_status(app, db)
    return _app_to_dict(app)


@router.put("/{app_id}")
async def update_app(app_id: int, req: UpdateRequest, db: AsyncSession = Depends(get_db)):
    app = await _get_or_404(app_id, db)

    if req.domain is not None:
        app.domain = req.domain
    if req.ssl_cert_path is not None:
        app.ssl_cert_path = req.ssl_cert_path
    if req.ssl_key_path is not None:
        app.ssl_key_path = req.ssl_key_path
    if req.start_command is not None:
        app.start_command = req.start_command
        app.app_type = pm.detect_app_type_from_command(req.start_command)
    if req.port is not None:
        app.port = req.port
    if req.env_vars is not None:
        app.env_vars = json.dumps(req.env_vars)
    resolved = _resolve_token(req.github_token, req.github_token_id)
    if resolved is not None:
        app.github_token = resolved
    if req.auto_start is not None:
        app.auto_start = req.auto_start
    if req.restart_policy is not None and req.restart_policy in ("no", "always", "on-failure"):
        app.restart_policy = req.restart_policy

    if app.domain and app.port:
        config = nm.generate_config(
            app.name, app.domain, app.port,
            app.ssl_cert_path, app.ssl_key_path,
            app_id=app.id, mode=_get_nginx_mode(app),
        )
        ok, _ = nm.write_nginx_config(app.name, config)
        app.nginx_enabled = ok

    await db.commit()
    return _app_to_dict(app)


@router.delete("/{app_id}")
async def delete_app(app_id: int, db: AsyncSession = Depends(get_db)):
    app = await _get_or_404(app_id, db)

    if app.status == "running" and app.pid:
        pm.stop_app(app_id, app.pid)

    if app.nginx_enabled:
        nm.remove_nginx_config(app.name)

    app_dir = pm.get_app_dir(app.name)
    if os.path.exists(app_dir):
        shutil.rmtree(app_dir)

    await db.delete(app)
    await db.commit()
    return {"message": f"App '{app.name}' deleted"}


@router.post("/{app_id}/start")
async def start_app(app_id: int, db: AsyncSession = Depends(get_db)):
    app = await _get_or_404(app_id, db)

    if app.status == "running" and app.pid and pm.is_process_running(app.pid, app.id):
        raise HTTPException(400, "App is already running")

    if not app.start_command:
        raise HTTPException(400, "No start command configured")

    env_vars = json.loads(app.env_vars or "{}")
    pid = pm.start_app(app_id, app.name, app.start_command, app.working_dir, env_vars)

    app.pid = pid
    app.status = "running"
    await db.commit()
    return {"status": "running", "pid": pid}


@router.post("/{app_id}/stop")
async def stop_app(app_id: int, db: AsyncSession = Depends(get_db)):
    app = await _get_or_404(app_id, db)

    pm.stop_app(app_id, app.pid)
    app.status = "stopped"
    app.pid = None
    await db.commit()
    return {"status": "stopped"}


@router.post("/{app_id}/restart")
async def restart_app(app_id: int, db: AsyncSession = Depends(get_db)):
    app = await _get_or_404(app_id, db)

    if app.pid:
        pm.stop_app(app_id, app.pid)

    await asyncio.sleep(1)

    env_vars = json.loads(app.env_vars or "{}")
    pid = pm.start_app(app_id, app.name, app.start_command, app.working_dir, env_vars)

    app.pid = pid
    app.status = "running"
    await db.commit()
    return {"status": "running", "pid": pid}


@router.post("/{app_id}/pull")
async def git_pull(app_id: int, db: AsyncSession = Depends(get_db)):
    app = await _get_or_404(app_id, db)
    app_dir = pm.get_app_dir(app.name)

    if app.github_token:
        url = _build_clone_url(app.repo_url, app.github_token)
        subprocess.run(["git", "remote", "set-url", "origin", url], cwd=app_dir, capture_output=True)

    fetch = subprocess.run(["git", "fetch", "origin"], cwd=app_dir, capture_output=True, text=True)
    if fetch.returncode != 0:
        raise HTTPException(500, f"Git fetch failed: {fetch.stderr}")

    reset = subprocess.run(["git", "reset", "--hard", "@{u}"], cwd=app_dir, capture_output=True, text=True)
    if reset.returncode != 0:
        raise HTTPException(500, f"Git reset failed: {reset.stderr}")

    return {"message": "Pulled latest changes", "output": reset.stdout}


@router.post("/{app_id}/install-deps")
async def install_deps(app_id: int, db: AsyncSession = Depends(get_db)):
    app = await _get_or_404(app_id, db)
    app_dir = pm.get_app_dir(app.name)
    output_lines = []

    if os.path.exists(os.path.join(app_dir, "package.json")):
        r = subprocess.run(["npm", "install"], cwd=app_dir, capture_output=True, text=True)
        output_lines.append(r.stdout + r.stderr)
        if r.returncode != 0:
            raise HTTPException(500, f"npm install failed: {r.stderr}")

    if os.path.exists(os.path.join(app_dir, "requirements.txt")):
        r = subprocess.run(
            ["pip", "install", "-r", "requirements.txt"],
            cwd=app_dir, capture_output=True, text=True,
        )
        output_lines.append(r.stdout + r.stderr)
        if r.returncode != 0:
            raise HTTPException(500, f"pip install failed: {r.stderr}")

    if os.path.exists(os.path.join(app_dir, "Gemfile")):
        r = subprocess.run(["bundle", "install"], cwd=app_dir, capture_output=True, text=True)
        output_lines.append(r.stdout + r.stderr)

    if os.path.exists(os.path.join(app_dir, "composer.json")):
        r = subprocess.run(["composer", "install"], cwd=app_dir, capture_output=True, text=True)
        output_lines.append(r.stdout + r.stderr)

    if not output_lines:
        return {"message": "No dependency files found", "output": ""}

    return {"message": "Dependencies installed", "output": "\n".join(output_lines)}


@router.get("/{app_id}/nginx-config")
async def get_nginx_config(app_id: int, db: AsyncSession = Depends(get_db)):
    app = await _get_or_404(app_id, db)
    safe = nm._safe_name(app.name)
    config_path = os.path.join(nm.NGINX_SITES_DIR, safe)
    if not os.path.exists(config_path):
        generated = None
        if app.domain and app.port:
            generated = nm.generate_config(
                app.name, app.domain, app.port,
                app.ssl_cert_path, app.ssl_key_path,
                app_id=app.id, mode=_get_nginx_mode(app),
            )
        return {"exists": False, "path": config_path, "content": generated, "active": False}
    with open(config_path) as f:
        content = f.read()
    enabled_path = os.path.join(nm.NGINX_ENABLED_DIR, safe)
    return {"exists": True, "path": config_path, "content": content, "active": os.path.exists(enabled_path)}


@router.put("/{app_id}/nginx-config")
async def save_nginx_config(app_id: int, payload: dict, db: AsyncSession = Depends(get_db)):
    app = await _get_or_404(app_id, db)
    content = payload.get("content", "")
    ok, msg = nm.write_nginx_config(app.name, content)
    if ok:
        app.nginx_enabled = True
        await db.commit()
    return {"ok": ok, "message": msg}


@router.get("/{app_id}/stats")
async def get_stats(app_id: int, db: AsyncSession = Depends(get_db)):
    app = await _get_or_404(app_id, db)
    if app.pid and pm.is_process_running(app.pid, app.id):
        stats = pm.get_process_stats(app.pid)
        return {"status": "running", **stats}
    return {"status": "stopped"}


async def _get_or_404(app_id: int, db: AsyncSession) -> Application:
    result = await db.execute(select(Application).where(Application.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(404, "App not found")
    return app


def _app_to_dict(app: Application) -> dict:
    return {
        "id": app.id,
        "name": app.name,
        "repo_url": app.repo_url,
        "domain": app.domain,
        "app_type": app.app_type,
        "start_command": app.start_command,
        "port": app.port,
        "status": app.status,
        "pid": app.pid,
        "working_dir": app.working_dir,
        "env_vars": json.loads(app.env_vars or "{}"),
        "nginx_enabled": app.nginx_enabled,
        "auto_start":     app.auto_start,
        "restart_policy": app.restart_policy or "no",
        "maintenance_mode": app.maintenance_mode or False,
        "update_mode":      app.update_mode or False,
        "downtime_page":    json.loads(app.downtime_page or "{}"),
        "update_page":      json.loads(app.update_page   or "{}"),
        "ssl_cert_path": app.ssl_cert_path,
        "ssl_key_path": app.ssl_key_path,
        "github_token": "***" if app.github_token else None,
        "created_at": app.created_at.isoformat() if app.created_at else None,
        "updated_at": app.updated_at.isoformat() if app.updated_at else None,
    }


# ── Maintenance page endpoints ─────────────────────────────────────────────

@router.get("/{app_id}/maintenance-pages")
async def get_maintenance_pages(app_id: int, db: AsyncSession = Depends(get_db)):
    app = await _get_or_404(app_id, db)
    return {
        "maintenance_mode": app.maintenance_mode or False,
        "update_mode":      app.update_mode or False,
        "downtime_page":    json.loads(app.downtime_page or "{}"),
        "update_page":      json.loads(app.update_page   or "{}"),
    }


@router.put("/{app_id}/maintenance-pages")
async def save_maintenance_pages(
    app_id: int,
    req: MaintenanceSettings,
    db: AsyncSession = Depends(get_db),
):
    app = await _get_or_404(app_id, db)
    app.downtime_page = json.dumps(req.downtime_page.model_dump())
    app.update_page   = json.dumps(req.update_page.model_dump())

    downtime_html = nm.generate_maintenance_html(
        req.downtime_page.title   or "Down for Maintenance",
        req.downtime_page.message or "We'll be back shortly.",
        req.downtime_page.color   or "#f85149",
        req.downtime_page.custom_html,
        "downtime",
    )
    update_html = nm.generate_maintenance_html(
        req.update_page.title   or "Updating\u2026",
        req.update_page.message or "We\u2019re deploying a new version. Check back soon.",
        req.update_page.color   or "#f0883e",
        req.update_page.custom_html,
        "update",
    )
    ok, msg = nm.write_maintenance_files(app_id, downtime_html, update_html)
    if not ok:
        await db.commit()
        return {"ok": False, "message": msg}

    # Regenerate and reload nginx if configured, so changes take effect immediately
    if app.nginx_enabled and app.domain:
        mode   = _get_nginx_mode(app)
        config = nm.generate_config(
            app.name, app.domain, app.port,
            app.ssl_cert_path, app.ssl_key_path,
            app_id=app_id, mode=mode,
        )
        nginx_ok, nginx_msg = nm.write_nginx_config(app.name, config)
        if not nginx_ok:
            await db.commit()
            return {"ok": False, "message": f"Files saved but nginx reload failed: {nginx_msg}"}

    await db.commit()
    return {"ok": True, "message": "Saved"}


@router.post("/{app_id}/maintenance-mode/toggle")
async def toggle_maintenance_mode(app_id: int, db: AsyncSession = Depends(get_db)):
    app = await _get_or_404(app_id, db)
    if not app.nginx_enabled or not app.domain:
        raise HTTPException(400, "Nginx must be configured to use maintenance mode")

    app.maintenance_mode = not (app.maintenance_mode or False)
    if app.maintenance_mode:
        app.update_mode = False  # mutex: only one mode at a time

    _ensure_maintenance_files(app, app_id)
    mode   = _get_nginx_mode(app)
    config = nm.generate_config(
        app.name, app.domain, app.port,
        app.ssl_cert_path, app.ssl_key_path,
        app_id=app_id, mode=mode,
    )
    ok, msg = nm.write_nginx_config(app.name, config)
    if not ok:
        raise HTTPException(500, f"Nginx config failed: {msg}")

    await db.commit()
    return _app_to_dict(app)


@router.post("/{app_id}/update-mode/toggle")
async def toggle_update_mode(app_id: int, db: AsyncSession = Depends(get_db)):
    app = await _get_or_404(app_id, db)
    if not app.nginx_enabled or not app.domain:
        raise HTTPException(400, "Nginx must be configured to use update mode")

    app.update_mode = not (app.update_mode or False)
    if app.update_mode:
        app.maintenance_mode = False  # mutex: only one mode at a time

    _ensure_maintenance_files(app, app_id)
    mode   = _get_nginx_mode(app)
    config = nm.generate_config(
        app.name, app.domain, app.port,
        app.ssl_cert_path, app.ssl_key_path,
        app_id=app_id, mode=mode,
    )
    ok, msg = nm.write_nginx_config(app.name, config)
    if not ok:
        raise HTTPException(500, f"Nginx config failed: {msg}")

    await db.commit()
    return _app_to_dict(app)


@router.get("/{app_id}/maintenance-pages/preview/{page_type}")
async def preview_maintenance_page(
    app_id: int,
    page_type: str,
    db: AsyncSession = Depends(get_db),
):
    """Return the rendered HTML for a maintenance page — opens directly in the browser."""
    from fastapi.responses import HTMLResponse

    if page_type not in ("downtime", "update"):
        raise HTTPException(400, "page_type must be 'downtime' or 'update'")

    app = await _get_or_404(app_id, db)
    raw = app.downtime_page if page_type == "downtime" else (app.update_page or "{}")
    cfg = json.loads(raw or "{}")

    if page_type == "downtime":
        html = nm.generate_maintenance_html(
            cfg.get("title")   or "Down for Maintenance",
            cfg.get("message") or "We'll be back shortly.",
            cfg.get("color")   or "#f85149",
            cfg.get("custom_html"),
            "downtime",
        )
    else:
        html = nm.generate_maintenance_html(
            cfg.get("title")   or "Updating\u2026",
            cfg.get("message") or "We\u2019re deploying a new version. Check back soon.",
            cfg.get("color")   or "#f0883e",
            cfg.get("custom_html"),
            "update",
        )
    return HTMLResponse(content=html)
