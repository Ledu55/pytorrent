import asyncio
import json
from dataclasses import asdict

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from torrent.manager import TorrentManager

router = APIRouter(prefix="/api")
_manager: TorrentManager | None = None


def set_manager(manager: TorrentManager) -> None:
    global _manager
    _manager = manager


def _get_manager() -> TorrentManager:
    if _manager is None:
        raise RuntimeError("Manager not initialised")
    return _manager


@router.post("/torrents")
async def add_torrent(
    file: UploadFile = File(...),
    save_path: str = Form(default="/tmp/downloads"),
):
    if not file.filename or not file.filename.endswith(".torrent"):
        raise HTTPException(status_code=400, detail="Only .torrent files are accepted")
    data = await file.read()
    try:
        info_hash = _get_manager().add_torrent(data, save_path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
