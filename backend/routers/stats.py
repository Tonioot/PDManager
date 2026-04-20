import asyncio
import time
import psutil
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from database import AsyncSessionLocal
from models import Application
import process_manager as pm

router = APIRouter(tags=["stats"])


@router.websocket("/ws/apps/{app_id}/stats")
async def stream_stats(app_id: int, websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Application).where(Application.id == app_id))
                app = result.scalar_one_or_none()

            if not app:
                await websocket.send_json({"error": "App not found"})
                break

            running = app.pid and pm.is_process_running(app.pid)
            if running:
                stats = pm.get_process_stats(app.pid)
                sys_mem = psutil.virtual_memory()
                await websocket.send_json({
                    "status": "running",
                    "pid": app.pid,
                    "cpu_percent": stats.get("cpu_percent", 0),
                    "memory_mb": stats.get("memory_mb", 0),
                    "uptime_seconds": stats.get("uptime_seconds", 0),
                    "proc_status": stats.get("status", "unknown"),
                    "system_cpu_percent": psutil.cpu_percent(interval=None),
                    "system_memory_total_mb": round(sys_mem.total / 1024 / 1024),
                    "system_memory_used_mb": round(sys_mem.used / 1024 / 1024),
                    "system_memory_percent": sys_mem.percent,
                })
            else:
                await websocket.send_json({"status": "stopped"})

            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass


@router.websocket("/ws/system/stats")
async def stream_system_stats(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            await websocket.send_json({
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_total_mb": round(mem.total / 1024 / 1024),
                "memory_used_mb": round(mem.used / 1024 / 1024),
                "memory_percent": mem.percent,
                "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
                "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 1),
                "disk_percent": disk.percent,
                "timestamp": time.time(),
            })
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
