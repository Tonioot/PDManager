import asyncio
import psutil
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import process_manager as pm

router = APIRouter(tags=["stats"])


@router.websocket("/ws/apps/{app_id}/stats")
async def stream_stats(app_id: int, websocket: WebSocket):
    await websocket.accept()
    q = pm.subscribe_stats(app_id)

    # Flush stored history immediately — charts populate at once
    for point in pm.get_recent_stats(app_id):
        try:
            await websocket.send_json(point)
        except Exception:
            pm.unsubscribe_stats(app_id, q)
            return

    try:
        while True:
            data = await q.get()
            await websocket.send_json(data)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        pm.unsubscribe_stats(app_id, q)


@router.websocket("/ws/system/stats")
async def stream_system_stats(websocket: WebSocket):
    await websocket.accept()
    try:
        # Prime the cpu_percent measurement so the first value is meaningful
        psutil.cpu_percent(interval=None)
        while True:
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            # Run blocking cpu_percent in a thread to avoid blocking the event loop
            cpu = await asyncio.to_thread(psutil.cpu_percent, 1)
            await websocket.send_json({
                "cpu_percent": cpu,
                "memory_total_mb": round(mem.total / 1024 / 1024),
                "memory_used_mb": round(mem.used / 1024 / 1024),
                "memory_percent": mem.percent,
                "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
                "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 1),
                "disk_percent": disk.percent,
            })
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
