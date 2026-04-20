import os
import mimetypes
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Application
import process_manager as pm

router = APIRouter(prefix="/api/apps", tags=["files"])


@router.get("/{app_id}/files")
async def list_files(
    app_id: int,
    path: str = Query("", description="Relative path inside the app directory"),
    db: AsyncSession = Depends(get_db),
):
    app = await _get_or_404(app_id, db)
    base_dir = pm.get_app_dir(app.name)
    target = os.path.normpath(os.path.join(base_dir, path.lstrip("/")))

    if not target.startswith(base_dir):
        raise HTTPException(400, "Path traversal not allowed")

    if not os.path.exists(target):
        raise HTTPException(404, "Path not found")

    if os.path.isfile(target):
        raise HTTPException(400, "Path is a file, not a directory")

    entries = []
    for name in sorted(os.listdir(target)):
        full = os.path.join(target, name)
        stat = os.stat(full)
        entries.append({
            "name": name,
            "path": os.path.relpath(full, base_dir),
            "is_dir": os.path.isdir(full),
            "size": stat.st_size if os.path.isfile(full) else None,
            "modified": stat.st_mtime,
        })

    return {"path": os.path.relpath(target, base_dir), "entries": entries}


@router.get("/{app_id}/files/content")
async def get_file_content(
    app_id: int,
    path: str = Query(..., description="Relative file path"),
    db: AsyncSession = Depends(get_db),
):
    app = await _get_or_404(app_id, db)
    base_dir = pm.get_app_dir(app.name)
    target = os.path.normpath(os.path.join(base_dir, path.lstrip("/")))

    if not target.startswith(base_dir):
        raise HTTPException(400, "Path traversal not allowed")

    if not os.path.isfile(target):
        raise HTTPException(404, "File not found")

    size = os.path.getsize(target)
    if size > 1_000_000:
        raise HTTPException(413, "File too large to display (>1MB)")

    mime, _ = mimetypes.guess_type(target)
    is_text = (
        (mime and mime.startswith("text")) or
        target.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml",
                          ".yml", ".toml", ".env", ".sh", ".md", ".txt", ".css",
                          ".html", ".xml", ".cfg", ".ini", ".conf", ".go", ".rs"))
    )

    if not is_text:
        return {"path": path, "content": None, "binary": True, "mime": mime}

    with open(target, "r", errors="replace") as f:
        content = f.read()

    return {"path": path, "content": content, "binary": False, "mime": mime or "text/plain"}


async def _get_or_404(app_id: int, db: AsyncSession) -> Application:
    result = await db.execute(select(Application).where(Application.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(404, "App not found")
    return app
