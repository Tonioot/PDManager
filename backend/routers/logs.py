import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from database import AsyncSessionLocal
from models import Application
from sqlalchemy import select
import process_manager as pm

router = APIRouter(tags=["logs"])


@router.websocket("/ws/apps/{app_id}/logs")
async def stream_logs(app_id: int, websocket: WebSocket):
    await websocket.accept()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Application).where(Application.id == app_id))
        app = result.scalar_one_or_none()
        if not app:
            await websocket.send_text("App not found\n")
            await websocket.close()
            return

        # Subscribe before snapshot so we don't miss lines produced during send
        q = pm.subscribe_logs(app_id)
        recent = pm.get_recent_logs(app_id, app.name)
        for line in recent:
            await websocket.send_text(line + "\n")

    try:
        while True:
            line = await q.get()
            await websocket.send_text(line + "\n")
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        pm.unsubscribe_logs(app_id, q)
