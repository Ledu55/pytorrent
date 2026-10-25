import asyncio
import logging
import threading
import time
from dataclasses import asdict
from pathlib import Path

import libtorrent as lt

from .config import Settings
from .session import TorrentSession
from .handle import TorrentHandle, TorrentStatus, status_from_lt

logger = logging.getLogger(__name__)

# How often (in poll ticks, ~1s each) dirty torrents get their resume data saved
_RESUME_SAVE_INTERVAL = 30


class DuplicateTorrentError(Exception):
    pass


class TorrentManager:
    def __init__(self, settings: Settings | None = None, resume_dir: Path | None = None) -> None:
        self.settings = settings or Settings()
        self._session = TorrentSession(self.settings)
        # None disables persistence (tests, throwaway sessions)
        self._resume_dir = resume_dir
        self._handles: dict[str, TorrentHandle] = {}
        self._statuses: dict[str, TorrentStatus] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: list[asyncio.Queue] = []

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._load_resume_data()
        self._stop_event.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._poll_thread:
            self._poll_thread.join(timeout=3.0)
            if self._poll_thread.is_alive():
                logger.warning("Poll thread did not stop within timeout")
        self._session.pause()
        self._save_all_resume_data()

    # ── Adding / removing ─────────────────────────────────────────────────

    def add_torrent(self, torrent_bytes: bytes, save_path: str) -> str:
        torrent_info = lt.torrent_info(torrent_bytes)
        return self._add({"ti": torrent_info, "save_path": save_path})

    def add_magnet(self, uri: str, save_path: str) -> str:
        params = lt.parse_magnet_uri(uri)
        params.save_path = save_path
        return self._add(params)

    def _add(self, params) -> str:
        with self._lock:
            raw_handle = self._session.add_torrent(params)
            handle = TorrentHandle(raw_handle)
            info_hash = handle.info_hash
            if info_hash in self._handles:
                raise DuplicateTorrentError(info_hash)
            self._handles[info_hash] = handle
            # Seed the status map so the torrent is visible before the first poll tick
            self._statuses[info_hash] = handle.get_status()
        self._request_resume_save(handle)
        return info_hash

    def remove_torrent(self, info_hash: str, delete_files: bool = False) -> bool:
        with self._lock:
            handle = self._handles.pop(info_hash, None)
            self._statuses.pop(info_hash, None)
        if handle is None:
            return False
        self._session.remove_torrent(handle.raw_handle(), delete_files)
        if self._resume_dir:
            self._resume_file(info_hash).unlink(missing_ok=True)
        return True

    # ── Per-torrent actions ───────────────────────────────────────────────

    def _handle(self, info_hash: str) -> TorrentHandle:
        with self._lock:
            handle = self._handles.get(info_hash)
        if handle is None:
            raise KeyError(info_hash)
        return handle

    def pause(self, info_hash: str) -> None:
        self._handle(info_hash).pause()

    def resume(self, info_hash: str) -> None:
        self._handle(info_hash).resume()

    def recheck(self, info_hash: str) -> None:
        self._handle(info_hash).recheck()

    def reannounce(self, info_hash: str) -> None:
        self._handle(info_hash).reannounce()

    def pause_all(self) -> None:
        with self._lock:
            handles = list(self._handles.values())
        for h in handles:
            h.pause()

    def resume_all(self) -> None:
        with self._lock:
            handles = list(self._handles.values())
        for h in handles:
            h.resume()

    def details(self, info_hash: str) -> dict:
        h = self._handle(info_hash)
        return {"files": h.files(), "peers": h.peers(), "trackers": h.trackers()}

    def set_file_priorities(self, info_hash: str, priorities: dict[int, int]) -> None:
        h = self._handle(info_hash)
        h.set_file_priorities(priorities)
        self._request_resume_save(h)

    def get_status(self, info_hash: str) -> TorrentStatus | None:
        with self._lock:
            return self._statuses.get(info_hash)

    def get_all_statuses(self) -> list[TorrentStatus]:
        with self._lock:
            return list(self._statuses.values())

    # ── Session-wide ──────────────────────────────────────────────────────

    def apply_settings(self, settings: Settings) -> None:
        self.settings = settings
        self._session.apply_settings(settings)

    def session_info(self) -> dict:
        return {
            "listening": self._session.is_listening(),
            "listen_port": self._session.listen_port(),
            "dht_nodes": self._session.dht_nodes(),
        }

    # ── SSE subscribers ───────────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=10)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    # ── Resume data ───────────────────────────────────────────────────────

    def _resume_file(self, info_hash: str) -> Path:
        return self._resume_dir / f"{info_hash}.fastresume"

    def _request_resume_save(self, handle: TorrentHandle) -> None:
        if not self._resume_dir:
            return
        try:
            # save_info_dict embeds the metadata, so magnets don't need refetching
            handle.raw_handle().save_resume_data(lt.torrent_handle.save_info_dict)
        except Exception:
            logger.exception("Could not request resume data for %s", handle.info_hash)

    def _write_resume(self, alert) -> None:
        ih = str(alert.handle.info_hash())
        with self._lock:
            if ih not in self._handles:
                return  # removed while the save was in flight
        try:
            self._resume_dir.mkdir(parents=True, exist_ok=True)
            path = self._resume_file(ih)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(lt.write_resume_data_buf(alert.params))
            tmp.replace(path)
        except Exception:
            logger.exception("Could not write resume data for %s", ih)

    def _load_resume_data(self) -> None:
        if not self._resume_dir or not self._resume_dir.is_dir():
            return
        for path in sorted(self._resume_dir.glob("*.fastresume")):
            try:
                params = lt.read_resume_data(path.read_bytes())
                self._add(params)
            except DuplicateTorrentError:
                pass
            except Exception:
                logger.exception("Skipping unreadable resume file %s", path.name)
        logger.info("Restored %d torrent(s)", len(self._handles))

    def _save_all_resume_data(self) -> None:
        if not self._resume_dir:
            return
        with self._lock:
            handles = list(self._handles.values())
        pending = 0
        for h in handles:
            if h.raw_handle().need_save_resume_data():
                self._request_resume_save(h)
                pending += 1
        deadline = time.monotonic() + 5.0
        while pending and time.monotonic() < deadline:
            for alert in self._session.pop_alerts():
                if isinstance(alert, lt.save_resume_data_alert):
                    self._write_resume(alert)
                    pending -= 1
                elif isinstance(alert, lt.save_resume_data_failed_alert):
                    pending -= 1
            time.sleep(0.05)

    # ── Poll loop ─────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        tick = 0
        while not self._stop_event.is_set():
            try:
                # post_torrent_updates MUST come before pop_alerts
                self._session.post_torrent_updates()
                alerts = self._session.pop_alerts()

                updated: list[TorrentStatus] = []
                for alert in alerts:
                    if isinstance(alert, lt.state_update_alert):
                        # Build statuses from the alert payload itself; querying the
                        # handle here races with remove_torrent (invalid handle).
                        with self._lock:
                            for raw_status in alert.status:
                                ih = str(raw_status.info_hash)
                                if ih not in self._handles:
                                    continue
                                status = status_from_lt(raw_status)
                                self._statuses[ih] = status
                                updated.append(status)
                    elif isinstance(alert, lt.save_resume_data_alert):
                        self._write_resume(alert)
                    elif isinstance(
                        alert, (lt.metadata_received_alert, lt.torrent_finished_alert)
                    ):
                        self._request_resume_save(TorrentHandle(alert.handle))
                    elif isinstance(alert, (lt.torrent_error_alert, lt.file_error_alert)):
                        logger.warning("%s", alert.message())

                tick += 1
                if tick % _RESUME_SAVE_INTERVAL == 0:
                    with self._lock:
                        handles = list(self._handles.values())
                    for h in handles:
                        if h.raw_handle().need_save_resume_data():
                            self._request_resume_save(h)

                if updated and self._loop:
                    self._loop.call_soon_threadsafe(self._broadcast, list(updated))
            except Exception:
                logger.exception("Torrent poll tick failed")

            self._stop_event.wait(timeout=1.0)

    def _broadcast(self, statuses: list[TorrentStatus]) -> None:
        payload = [asdict(s) for s in statuses]
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # Slow consumer: drop its oldest frame so it skips stale updates
                # instead of being silently unsubscribed
                try:
                    q.get_nowait()
                    q.put_nowait(payload)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass
