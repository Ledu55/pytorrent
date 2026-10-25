from dataclasses import dataclass

import libtorrent as lt

_STATE_MAP = {
    lt.torrent_status.checking_files: "checking",
    lt.torrent_status.downloading_metadata: "downloading metadata",
    lt.torrent_status.downloading: "downloading",
    lt.torrent_status.finished: "finished",
    lt.torrent_status.seeding: "seeding",
    lt.torrent_status.checking_resume_data: "checking resume",
}

# libtorrent file priorities: 0 = skip, 4 = default, 7 = top
PRIORITY_SKIP = 0
PRIORITY_NORMAL = 4
PRIORITY_HIGH = 7


@dataclass(frozen=True)
class TorrentStatus:
    info_hash: str
    name: str
    state: str
    progress: float       # 0.0–1.0
    download_rate: int    # bytes/sec
    upload_rate: int      # bytes/sec
    num_peers: int
    total_size: int       # bytes
    downloaded: int       # bytes
    save_path: str
    error: str
    num_seeds: int = 0
    uploaded: int = 0     # bytes, all time
    ratio: float = 0.0
    eta: int = -1         # seconds, -1 when unknown
    added_time: int = 0   # unix timestamp
    queue_position: int = -1


def _state_str(s) -> str:
    flags = getattr(s, "flags", 0)
    if flags & lt.torrent_flags.paused:
        # A paused auto-managed torrent is waiting for a free queue slot
        return "queued" if flags & lt.torrent_flags.auto_managed else "paused"
    return _STATE_MAP.get(s.state, str(s.state))


def status_from_lt(s: lt.torrent_status) -> TorrentStatus:
    """Map a libtorrent torrent_status snapshot to a TorrentStatus."""
    total = s.total_wanted if s.total_wanted > 0 else 0
    downloaded = int(total * s.progress)
    error = s.errc.message() if s.errc.value() != 0 else ""
    uploaded = getattr(s, "all_time_upload", 0)
    all_down = getattr(s, "all_time_download", 0)
    ratio = uploaded / all_down if all_down > 0 else 0.0
    remaining = total - downloaded
    eta = int(remaining / s.download_rate) if s.download_rate > 0 and remaining > 0 else -1
    return TorrentStatus(
        info_hash=str(s.info_hash),
        name=s.name,
        state=_state_str(s),
        progress=s.progress,
        download_rate=s.download_rate,
        upload_rate=s.upload_rate,
        num_peers=s.num_peers,
        total_size=total,
        downloaded=downloaded,
        save_path=s.save_path,
        error=error,
        num_seeds=getattr(s, "num_seeds", 0),
        uploaded=uploaded,
        ratio=round(ratio, 3),
        eta=eta,
        added_time=getattr(s, "added_time", 0),
        queue_position=int(getattr(s, "queue_position", -1)),
    )


class TorrentHandle:
    def __init__(self, handle: lt.torrent_handle) -> None:
        self._handle = handle

    @property
    def info_hash(self) -> str:
        return str(self._handle.info_hash())

    def get_status(self) -> TorrentStatus:
        return status_from_lt(self._handle.status())

    def is_complete(self) -> bool:
        s = self._handle.status()
        return s.state in (lt.torrent_status.finished, lt.torrent_status.seeding)

    def pause(self) -> None:
        # Drop auto-management, or the queue would immediately resume it
        self._handle.unset_flags(lt.torrent_flags.auto_managed)
        self._handle.pause()

    def resume(self) -> None:
        self._handle.set_flags(lt.torrent_flags.auto_managed)
        self._handle.resume()

    def recheck(self) -> None:
        self._handle.force_recheck()

    def reannounce(self) -> None:
        self._handle.force_reannounce()

    def files(self) -> list[dict]:
        ti = self._handle.torrent_file()
        if ti is None:
            return []  # magnet still fetching metadata
        fs = ti.files()
        progress = self._handle.file_progress()
        priorities = self._handle.get_file_priorities()
        result = []
        for i in range(fs.num_files()):
            size = fs.file_size(i)
            result.append(
                {
                    "index": i,
                    "path": fs.file_path(i),
                    "size": size,
                    "progress": progress[i] / size if size else 1.0,
                    "priority": int(priorities[i]),
                }
            )
        return result

    def set_file_priorities(self, priorities: dict[int, int]) -> None:
        current = list(self._handle.get_file_priorities())
        for index, prio in priorities.items():
            if 0 <= index < len(current):
                current[index] = prio
        self._handle.prioritize_files(current)

    def peers(self) -> list[dict]:
        result = []
        for p in self._handle.get_peer_info():
            ip, port = p.ip
            client = p.client
            if isinstance(client, bytes):
                client = client.decode("utf-8", "replace")
            result.append(
                {
                    "address": f"{ip}:{port}",
                    "client": client,
                    "progress": p.progress,
                    "download_rate": p.down_speed,
                    "upload_rate": p.up_speed,
                }
            )
        return result

    def trackers(self) -> list[dict]:
        result = []
        for t in self._handle.trackers():
            message = ""
            for ep in t.get("endpoints", []):
                for ih in ep.get("info_hashes", []):
                    if ih.get("message"):
                        message = ih["message"]
            result.append({"url": t["url"], "tier": t.get("tier", 0), "message": message})
        return result

    def raw_handle(self) -> lt.torrent_handle:
        return self._handle
