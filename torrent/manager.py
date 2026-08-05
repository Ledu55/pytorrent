import asyncio
import threading
from dataclasses import asdict

import libtorrent as lt

from .session import TorrentSession
from .handle import TorrentHandle, TorrentStatus


class TorrentManager:
    def __init__(self) -> None:
        self._session = TorrentSession()
        self._handles: dict[str, TorrentHandle] = {}
        self._statuses: dict[str, TorrentStatus] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: list[asyncio.Queue] = []

    def start(self) -> None:
        self._loop = asyncio.get_event_loop()
        self._stop_event.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._poll_thread:
            self._poll_thread.join(timeout=3.0)
        self._session.pause()

    def add_torrent(self, torrent_bytes: bytes, save_path: str) -> str:
        torrent_info = lt.torrent_info(lt.bdecode(torrent_bytes))
        with self._lock:
            raw_handle = self._session.add_torrent(torrent_info, save_path)
            handle = TorrentHandle(raw_handle)
            info_hash = handle.info_hash
            self._handles[info_hash] = handle
        return info_hash

    def remove_torrent(self, info_hash: str) -> bool:
        with self._lock:
            handle = self._handles.pop(info_hash, None)
            self._statuses.pop(info_hash, None)
        if handle is None:
            return False
        self._session.remove_torrent(handle.raw_handle())
        return True

    def get_all_statuses(self) -> list[TorrentStatus]:
        with self._lock:
            return list(self._statuses.values())

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

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            # post_torrent_updates MUST come before pop_alerts
            self._session.post_torrent_updates()
            alerts = self._session.pop_alerts()

            updated: list[TorrentStatus] = []
            for alert in alerts:
                if isinstance(alert, lt.state_update_alert):
                    for raw_status in alert.status:
                        ih = str(raw_status.info_hash)
                        with self._lock:
                            handle = self._handles.get(ih)
                        if handle:
                            status = handle.get_status()
                            with self._lock:
                                self._statuses[ih] = status
                            updated.append(status)

            if updated and self._loop:
                self._loop.call_soon_threadsafe(self._broadcast, list(updated))

            self._stop_event.wait(timeout=1.0)

    def _broadcast(self, statuses: list[TorrentStatus]) -> None:
        payload = [asdict(s) for s in statuses]
        dead: list[asyncio.Queue] = []
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        if dead:
            with self._lock:
                for q in dead:
                    try:
                        self._subscribers.remove(q)
                    except ValueError:
                        pass
