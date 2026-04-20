import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

import json
from database import init_db, AsyncSessionLocal
from routers import applications, files, logs, stats
import process_manager as pm
from models import Application
from sqlalchemy import select

PORT = 7823
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    pm.set_main_loop(asyncio.get_event_loop())

    # On startup: clear stale PIDs, then auto-start apps that have auto_start=True.
    # Process detection works by checking psutil — if the stored PID no longer exists
    # in the OS process table (or is a zombie), the app is considered stopped.
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Application))
        all_apps = result.scalars().all()
        for a in all_apps:
            # Clear any PID that is no longer alive (PDManager was restarted)
            if a.pid and not pm.is_process_running(a.pid):
                a.status = "stopped"
                a.pid = None
            # Re-launch apps configured for auto-start
            if a.auto_start and a.status == "stopped" and a.start_command and a.working_dir:
                try:
                    env_vars = json.loads(a.env_vars or "{}")
                    pid = pm.start_app(a.id, a.name, a.start_command, a.working_dir, env_vars)
                    a.pid = pid
                    a.status = "running"
                except Exception:
                    pass
        await db.commit()

    yield


app = FastAPI(title="Process & Deployment Manager", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "port": PORT}


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
