import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

import json
from database import init_db, AsyncSessionLocal
from routers import applications, files, logs, stats
import process_manager as pm
import nginx_manager as nm
from models import Application
from sqlalchemy import select

PORT = 7823
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    pm.set_main_loop(asyncio.get_event_loop())
    pm.load_registry()  # restore PID tracking from previous session

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Application))
        all_apps = result.scalars().all()
        for a in all_apps:
            if a.pid:
                if pm.is_process_running(a.pid, a.id):
                    # Still alive — keep running status
                    a.status = "running"
                else:
                    # Stored PID is dead — try port-based recovery before giving up
                    recovered_pid = pm.find_process_by_port(a.port) if a.port else None
                    if recovered_pid:
                        a.pid = recovered_pid
                        a.status = "running"
                    else:
                        a.status = "stopped"
                        a.pid = None

            # Auto-start apps that are supposed to be running
            if a.auto_start and a.status == "stopped" and a.start_command and a.working_dir:
                try:
                    env_vars = json.loads(a.env_vars or "{}")
                    pid = pm.start_app(a.id, a.name, a.start_command, a.working_dir, env_vars)
                    a.pid = pid
                    a.status = "running"
                except Exception:
                    pass

        await db.commit()

    monitor_task = asyncio.create_task(_crash_monitor())
    yield
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Process & Deployment Manager", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


import time as _time

# restart_history: app_id -> list of timestamps of recent restarts
_restart_history: dict[int, list[float]] = {}
MAX_RESTARTS_PER_WINDOW = 5
RESTART_WINDOW_SECONDS  = 60


async def _crash_monitor():
    """Background task: detect crashed apps and restart them per their policy."""
    await asyncio.sleep(5)  # let startup settle
    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Application))
                apps = result.scalars().all()
                for a in apps:
                    if a.status != "running" or not a.pid:
                        continue
                    if pm.is_process_running(a.pid, a.id):
                        continue

                    # Process died — check restart policy
                    policy = a.restart_policy or "no"

                    if policy == "no":
                        a.status = "stopped"
                        a.pid = None
                        pm._push_line(a.id, "⚠ Process exited.")
                        await db.commit()
                        continue

                    # on-failure or always: check crash cooldown
                    now = _time.time()
                    history = _restart_history.setdefault(a.id, [])
                    history[:] = [t for t in history if now - t < RESTART_WINDOW_SECONDS]

                    if len(history) >= MAX_RESTARTS_PER_WINDOW:
                        a.status = "error"
                        a.pid = None
                        pm._push_line(a.id, f"✖ Crashed {MAX_RESTARTS_PER_WINDOW}× in {RESTART_WINDOW_SECONDS}s — giving up to prevent loop.")
                        await db.commit()
                        continue

                    history.append(now)
                    attempt = len(history)
                    pm._push_line(a.id, f"⟳ Process exited — restarting (attempt {attempt}/{MAX_RESTARTS_PER_WINDOW})…")
                    await asyncio.sleep(min(2 ** attempt, 30))  # exponential backoff

                    try:
                        env_vars = json.loads(a.env_vars or "{}")
                        new_pid = pm.start_app(a.id, a.name, a.start_command, a.working_dir, env_vars)
                        a.pid = new_pid
                        a.status = "running"
                        pm._push_line(a.id, f"✓ Restarted successfully (pid {new_pid}).")
                    except Exception as e:
                        a.status = "error"
                        a.pid = None
                        pm._push_line(a.id, f"✖ Restart failed: {e}")
                    await db.commit()
        except asyncio.CancelledError:
            return
        except Exception:
            pass
        await asyncio.sleep(5)


class PDManagerNginxRequest(BaseModel):
    domain: str
    ssl_cert_path: Optional[str] = None
    ssl_key_path: Optional[str] = None


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "port": PORT}


@app.get("/api/system/nginx-config")
async def get_pdmanager_nginx():
    config_path = os.path.join(nm.NGINX_SITES_DIR, "pdmanager")
    if not os.path.exists(config_path):
        return {"exists": False, "content": None}
    with open(config_path) as f:
        content = f.read()
    return {"exists": True, "content": content, "path": config_path}


@app.post("/api/system/nginx-config")
async def apply_pdmanager_nginx(req: PDManagerNginxRequest):
    config = nm.generate_config("pdmanager", req.domain, PORT, req.ssl_cert_path, req.ssl_key_path)
    ok, msg = nm.write_nginx_config("pdmanager", config)
    return {"ok": ok, "message": msg, "preview": config}


@app.post("/api/system/certs/upload")
async def upload_system_cert(file: UploadFile = File(...)):
    """Upload a cert/key file to ~/.pdmanager/certs/ and return its path."""
    allowed_exts = {".pem", ".crt", ".cer", ".key"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(400, "Only .pem, .crt, .cer, .key files are allowed")
    safe_name = os.path.basename(file.filename).replace("..", "").lstrip("/")
    dest_dir = os.path.expanduser("~/.pdmanager/certs")
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, safe_name)
    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)
    return {"path": dest_path}


app.include_router(applications.router)
app.include_router(files.router)
app.include_router(logs.router)
app.include_router(stats.router)

if os.path.isdir(FRONTEND_DIR):
    app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
    app.mount("/js",  StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")),  name="js")

    @app.get("/app.html", include_in_schema=False)
    async def app_page():
        return FileResponse(os.path.join(FRONTEND_DIR, "app.html"))

    @app.get("/", include_in_schema=False)
    async def index_page():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def catch_all(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
