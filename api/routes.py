import asyncio
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from torrent.manager import TorrentManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")
_manager: TorrentManager | None = None


def _default_download_root() -> Path:
    return Path.home() / "Downloads" / "pytorrent"


# All save paths must live under this root (metadata files are small; this caps
# the .torrent upload itself, not the downloaded payload)
DOWNLOAD_ROOT = Path(
    os.environ.get("PYTORRENT_DOWNLOAD_ROOT", str(_default_download_root()))
).resolve()
MAX_TORRENT_SIZE = 10 * 1024 * 1024


def set_manager(manager: TorrentManager) -> None:
    global _manager
    _manager = manager


def _get_manager() -> TorrentManager:
    if _manager is None:
        raise RuntimeError("Manager not initialised")
    return _manager


@router.get("/config")
async def get_config():
    return {"download_root": str(DOWNLOAD_ROOT)}


@router.post("/torrents")
async def add_torrent(
    file: UploadFile = File(...),
    save_path: str = Form(default=str(DOWNLOAD_ROOT)),
):
    if not file.filename or not file.filename.endswith(".torrent"):
        raise HTTPException(status_code=400, detail="Only .torrent files are accepted")
    resolved = Path(save_path).resolve()
    if resolved != DOWNLOAD_ROOT and not resolved.is_relative_to(DOWNLOAD_ROOT):
        raise HTTPException(
            status_code=400,
            detail=f"save_path must be inside {DOWNLOAD_ROOT}",
        )
    resolved.mkdir(parents=True, exist_ok=True)
    data = await file.read(MAX_TORRENT_SIZE + 1)
    if len(data) > MAX_TORRENT_SIZE:
        raise HTTPException(status_code=413, detail="Torrent file too large")
    try:
        info_hash = await run_in_threadpool(_get_manager().add_torrent, data, str(resolved))
    except Exception as exc:
        logger.exception("Failed to add torrent %r", file.filename)
        raise HTTPException(status_code=422, detail="Invalid or unloadable torrent file") from exc
    return {"info_hash": info_hash, "message": "Torrent added"}


@router.get("/torrents")
async def list_torrents():
    statuses = _get_manager().get_all_statuses()
    return [asdict(s) for s in statuses]


@router.delete("/torrents/{info_hash}")
async def remove_torrent(info_hash: str):
    removed = _get_manager().remove_torrent(info_hash)
    if not removed:
        raise HTTPException(status_code=404, detail="Torrent not found")
    return {"message": "Removed"}


@router.get("/events")
async def sse_stream(request: Request):
    manager = _get_manager()
    q = manager.subscribe()

    async def event_generator():
        # Send current state immediately on connect
        current = manager.get_all_statuses()
        yield f"data: {json.dumps([asdict(s) for s in current])}\n\n"

        try:
            while not await request.is_disconnected():
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    # keepalive comment prevents proxy from killing idle connections
                    yield ": keepalive\n\n"
        finally:
            manager.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
