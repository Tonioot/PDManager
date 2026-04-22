import asyncio
import json
import os
import time as _time
from collections import deque
from contextlib import asynccontextmanager
from typing import Optional

import psutil

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from database import AsyncSessionLocal, init_db
from models import Application
from routers import applications, files, logs, stats
import auth
import nginx_manager as nm
import process_manager as pm

PORT = 7823
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
_COOKIE_NAME = "pdm_token"
_COOKIE_OPTS = dict(httponly=True, samesite="strict", path="/")

# Restart-loop protection: max 5 restarts per 60s per app
_restart_history: dict[int, list[float]] = {}
MAX_RESTARTS_PER_WINDOW = 5
RESTART_WINDOW_SECONDS = 60


# ── Background stats collector ────────────────────────────────────────────────
async def _stats_collector():
    """Collect process stats for all running apps every 2 s, push to subscribers."""
    await asyncio.sleep(4)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Application).where(Application.status == "running")
                )
                apps = result.scalars().all()

            async def _one(a):
                if not a.pid:
                    return
                try:
                    s = await asyncio.to_thread(pm.get_process_stats, a.pid)
                    if not s:
                        return
                    mem = psutil.virtual_memory()
                    data = {
                        "status": "running",
                        "pid": a.pid,
                        **s,
                        "system_cpu_percent": psutil.cpu_percent(interval=None),
                        "system_memory_total_mb": round(mem.total / 1024 / 1024),
                        "system_memory_used_mb":  round(mem.used  / 1024 / 1024),
                        "system_memory_percent":  mem.percent,
                    }
                    pm._stats_history.setdefault(a.id, deque(maxlen=60)).append(data)
                    pm._push_stat(a.id, data)
                except Exception:
                    pass

            # Collect all apps concurrently — cpu_percent(interval=0.5) runs in threads
            await asyncio.gather(*[_one(a) for a in apps])
        except asyncio.CancelledError:
            return
        except Exception:
            pass
        await asyncio.sleep(2)


# ── Crash monitor ─────────────────────────────────────────────────────────────
async def _crash_monitor():
    await asyncio.sleep(5)
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

                    policy = a.restart_policy or "no"
                    if policy == "no":
                        a.status = "stopped"
                        a.pid = None
                        pm._push_line(a.id, "⚠ Process exited.")
                        await db.commit()
                        continue

                    now = _time.time()
                    history = _restart_history.setdefault(a.id, [])
                    history[:] = [t for t in history if now - t < RESTART_WINDOW_SECONDS]

                    if len(history) >= MAX_RESTARTS_PER_WINDOW:
                        a.status = "error"
                        a.pid = None
                        pm._push_line(a.id, f"✖ Crashed {MAX_RESTARTS_PER_WINDOW}× in {RESTART_WINDOW_SECONDS}s — giving up.")
                        await db.commit()
                        continue

                    history.append(now)
                    attempt = len(history)
                    pm._push_line(a.id, f"⟳ Process exited — restarting (attempt {attempt}/{MAX_RESTARTS_PER_WINDOW})…")
                    await asyncio.sleep(min(2 ** attempt, 30))

                    try:
                        env_vars = json.loads(a.env_vars or "{}")
                        new_pid = pm.start_app(a.id, a.name, a.start_command, a.working_dir, env_vars)
                        a.pid = new_pid
                        a.status = "running"
                        pm._push_line(a.id, f"✓ Restarted (pid {new_pid}).")
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


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    pm.set_main_loop(asyncio.get_event_loop())
    pm.load_registry()   # restore PID + shell_pid from disk before any process checks

    # First-run: generate a password if none exists
    if not auth.load_hashed_password():
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for _ in range(16))
        auth.save_hashed_password(auth.hash_password(password))
        print("\n" + "=" * 60)
        print("  PDManager — FIRST RUN")
        print(f"  Admin password: {password}")
        print("  Save this — it will not be shown again.")
        print("=" * 60 + "\n")

    # Recover running apps and auto-start
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Application))
        for a in result.scalars().all():
            if a.pid:
                if pm.is_process_running(a.pid, a.id):
                    a.status = "running"
                    # Re-attach a log tailer so live streaming works after restart
                    pm.attach_log_tailer(a.id, a.name, proc=None, seek_to_end=True)
                else:
                    recovered = pm.find_process_by_port(a.port) if a.port else None
                    if recovered:
                        a.pid = recovered
                        a.status = "running"
                        pm.attach_log_tailer(a.id, a.name, proc=None, seek_to_end=True)
                    else:
                        a.status = "stopped"
                        a.pid = None

            if a.auto_start and a.status == "stopped" and a.start_command and a.working_dir:
                try:
                    env_vars = json.loads(a.env_vars or "{}")
                    pid = pm.start_app(a.id, a.name, a.start_command, a.working_dir, env_vars)
                    a.pid = pid
                    a.status = "running"
                except Exception:
                    pass

        await db.commit()

    monitor_task  = asyncio.create_task(_crash_monitor())
    stats_task    = asyncio.create_task(_stats_collector())
    yield
    for task in (monitor_task, stats_task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Process & Deployment Manager", version="1.0.0", lifespan=lifespan)

# Auth middleware — blocks all /api/ and /ws/ except public paths
_PUBLIC = {"/api/health", "/api/auth/login", "/api/auth/logout", "/api/auth/check"}


class _AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (path.startswith("/api/") and path not in _PUBLIC) or path.startswith("/ws/"):
            token = request.cookies.get(_COOKIE_NAME)
            if not token or not auth.decode_token(token):
                return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return await call_next(request)


app.add_middleware(_AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth endpoints (public) ───────────────────────────────────────────────────
class LoginRequest(BaseModel):
    password: str


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "port": PORT}


@app.get("/api/auth/check")
async def auth_check(request: Request):
    token = request.cookies.get(_COOKIE_NAME)
    if not token or not auth.decode_token(token):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"authenticated": True}


@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request, response: Response):
    auth._check_rate_limit(request.client.host if request.client else "unknown")
    hashed = auth.load_hashed_password()
    if not hashed or not auth.verify_password(req.password, hashed):
        raise HTTPException(status_code=401, detail="Invalid password")
    token = auth.create_access_token()
    response.set_cookie(key=_COOKIE_NAME, value=token, max_age=auth.TOKEN_EXPIRE_SECONDS, **_COOKIE_OPTS)
    return {"ok": True, "expires_in": auth.TOKEN_EXPIRE_SECONDS}


@app.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie(key=_COOKIE_NAME, path="/")
    return {"ok": True}


class ChangePasswordRequest(BaseModel):
    password: str


@app.post("/api/auth/change-password")
async def change_password(req: ChangePasswordRequest, request: Request):
    token = request.cookies.get(_COOKIE_NAME)
    if not token or not auth.decode_token(token):
        raise HTTPException(status_code=401, detail="Not authenticated")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    auth.save_hashed_password(auth.hash_password(req.password))
    return {"ok": True}


# ── System endpoints ──────────────────────────────────────────────────────────
class PDManagerNginxRequest(BaseModel):
    domain: str
    ssl_cert_path: Optional[str] = None
    ssl_key_path: Optional[str] = None


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
    allowed_exts = {".pem", ".crt", ".cer", ".key"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(400, "Only .pem, .crt, .cer, .key files are allowed")
    safe_name = os.path.basename(file.filename or "cert").replace("..", "").lstrip("/")
    dest_dir = os.path.expanduser("~/.pdmanager/certs")
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, safe_name)
    with open(dest_path, "wb") as f:
        f.write(await file.read())
    return {"path": dest_path}


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(applications.router)
app.include_router(files.router)
app.include_router(logs.router)
app.include_router(stats.router)

# ── Static / SPA ──────────────────────────────────────────────────────────────
if os.path.isdir(FRONTEND_DIR):
    app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
    app.mount("/js",  StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")),  name="js")

    @app.get("/login", include_in_schema=False)
    @app.get("/login.html", include_in_schema=False)
    async def login_page():
        return FileResponse(os.path.join(FRONTEND_DIR, "login.html"))

    @app.get("/app.html", include_in_schema=False)
    async def app_page():
        return FileResponse(os.path.join(FRONTEND_DIR, "app.html"))

    @app.get("/", include_in_schema=False)
    async def index_page():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    app.get("/favicon.ico", include_in_schema=False)(lambda: FileResponse(os.path.join(FRONTEND_DIR, "assets", "favicon.svg")))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def catch_all(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
