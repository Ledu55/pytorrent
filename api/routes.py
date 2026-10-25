import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, fields
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from torrent.config import Settings, save_settings
from torrent.manager import DuplicateTorrentError, TorrentManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")
_manager: TorrentManager | None = None

# Metadata files are small; this caps the .torrent upload itself, not the payload
MAX_TORRENT_SIZE = 10 * 1024 * 1024
_LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


def set_manager(manager: TorrentManager) -> None:
    global _manager
    _manager = manager


def _get_manager() -> TorrentManager:
    if _manager is None:
        raise RuntimeError("Manager not initialised")
    return _manager


def _download_root() -> Path:
    return Path(_get_manager().settings.download_root).expanduser().resolve()


def _resolve_save_path(save_path: str | None) -> Path:
    """All save paths must live under the download root."""
    root = _download_root()
    if not save_path or not save_path.strip():
        resolved = root
    else:
        # Relative paths are taken as subfolders of the download root
        resolved = (root / Path(save_path.strip()).expanduser()).resolve()
    if resolved != root and not resolved.is_relative_to(root):
        raise HTTPException(
            status_code=400,
            detail=f"The save folder must be inside your download folder ({root}). "
            "Change the download folder in Settings to save elsewhere.",
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _duplicate_error() -> HTTPException:
    return HTTPException(status_code=409, detail="This torrent is already in your list.")


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Torrent not found")


# ── Config & settings ─────────────────────────────────────────────────────


@router.get("/config")
async def get_config():
    root = _download_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(root).free
    except OSError:
        free = None
    return {"download_root": str(root), "free_space": free}


@router.get("/session")
async def get_session():
    return _get_manager().session_info()


@router.get("/settings")
async def get_settings():
    return asdict(_get_manager().settings)


@router.put("/settings")
async def put_settings(payload: dict = Body(...)):
    current = asdict(_get_manager().settings)
    known = {f.name: f.type for f in fields(Settings)}
    for key, value in payload.items():
        if key in known:
            current[key] = value
    try:
        new = Settings(**current)
        # Coerce numeric fields that may arrive as strings from form inputs
        new.listen_port = int(new.listen_port)
        new.download_limit_kbps = int(new.download_limit_kbps)
        new.upload_limit_kbps = int(new.upload_limit_kbps)
        new.active_downloads = int(new.active_downloads)
        new.active_seeds = int(new.active_seeds)
        new.seed_ratio_limit = float(new.seed_ratio_limit)
        new.enable_upnp = bool(new.enable_upnp)
        new.validate()
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await run_in_threadpool(_get_manager().apply_settings, new)
    try:
        save_settings(new)
    except OSError as exc:
        logger.exception("Could not save settings")
        raise HTTPException(
            status_code=500, detail="Settings applied but couldn't be saved"
        ) from exc
    return asdict(new)


# ── Torrents ──────────────────────────────────────────────────────────────


@router.post("/torrents")
async def add_torrent(
    file: UploadFile = File(...),
    save_path: str | None = Form(default=None),
):
    if not file.filename or not file.filename.lower().endswith(".torrent"):
        raise HTTPException(status_code=400, detail="Only .torrent files are accepted")
    data = await file.read(MAX_TORRENT_SIZE + 1)
    if len(data) > MAX_TORRENT_SIZE:
        raise HTTPException(status_code=413, detail="Torrent file too large (max 10 MB)")
    resolved = _resolve_save_path(save_path)
    try:
        info_hash = await run_in_threadpool(_get_manager().add_torrent, data, str(resolved))
    except DuplicateTorrentError as exc:
        raise _duplicate_error() from exc
    except Exception as exc:
        logger.exception("Failed to add torrent %r", file.filename)
        raise HTTPException(
            status_code=422,
            detail=f"“{file.filename}” isn't a valid torrent file. It may be damaged or "
            "incomplete — try downloading it again.",
        ) from exc
    return {"info_hash": info_hash, "message": "Torrent added"}


@router.post("/torrents/magnet")
async def add_magnet(uri: str = Body(...), save_path: str | None = Body(default=None)):
    uri = uri.strip()
    if not uri.lower().startswith("magnet:?"):
        raise HTTPException(status_code=400, detail="That doesn't look like a magnet link")
    resolved = _resolve_save_path(save_path)
    try:
        info_hash = await run_in_threadpool(_get_manager().add_magnet, uri, str(resolved))
    except DuplicateTorrentError as exc:
        raise _duplicate_error() from exc
    except Exception as exc:
        logger.exception("Failed to add magnet")
        raise HTTPException(
            status_code=422, detail="This magnet link is invalid or incomplete"
        ) from exc
    return {"info_hash": info_hash, "message": "Torrent added"}


@router.get("/torrents")
async def list_torrents():
    statuses = _get_manager().get_all_statuses()
    return [asdict(s) for s in statuses]


@router.delete("/torrents/{info_hash}")
async def remove_torrent(info_hash: str, delete_files: bool = False):
    removed = _get_manager().remove_torrent(info_hash, delete_files)
    if not removed:
        raise _not_found()
    return {"message": "Removed"}


@router.post("/torrents/pause-all")
async def pause_all():
    _get_manager().pause_all()
    return {"message": "Paused"}


@router.post("/torrents/resume-all")
async def resume_all():
    _get_manager().resume_all()
    return {"message": "Resumed"}


_ACTIONS = {"pause", "resume", "recheck", "reannounce"}


@router.post("/torrents/{info_hash}/{action}")
async def torrent_action(info_hash: str, action: str, request: Request):
    manager = _get_manager()
    if action == "open":
        return await _open_folder(info_hash, request)
    if action not in _ACTIONS:
        raise HTTPException(status_code=404, detail="Unknown action")
    try:
        getattr(manager, action)(info_hash)
    except KeyError as exc:
        raise _not_found() from exc
    return {"message": "OK"}


@router.get("/torrents/{info_hash}/details")
async def torrent_details(info_hash: str):
    try:
        return await run_in_threadpool(_get_manager().details, info_hash)
    except KeyError as exc:
        raise _not_found() from exc


@router.put("/torrents/{info_hash}/files")
async def set_file_priorities(info_hash: str, priorities: dict[str, int] = Body(...)):
    try:
        parsed = {int(k): max(0, min(7, int(v))) for k, v in priorities.items()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid file priorities") from exc
    try:
        _get_manager().set_file_priorities(info_hash, parsed)
    except KeyError as exc:
        raise _not_found() from exc
    return {"message": "OK"}


async def _open_folder(info_hash: str, request: Request):
    # Opening a window on the host only makes sense for someone sitting at it
    if request.client and request.client.host not in _LOOPBACK:
        raise HTTPException(status_code=403, detail="Folders can only be opened locally")
    status = _get_manager().get_status(info_hash)
    if status is None:
        raise _not_found()
    target = Path(status.save_path)
    if status.name and (target / status.name).exists():
        target = target / status.name
    folder = target if target.is_dir() else target.parent
    try:
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606 - local path from libtorrent
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Couldn't open {folder}") from exc
    return {"message": "Opened"}


# ── Live updates ──────────────────────────────────────────────────────────


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
