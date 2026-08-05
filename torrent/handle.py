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


class TorrentHandle:
    def __init__(self, handle: lt.torrent_handle) -> None:
        self._handle = handle

    @property
    def info_hash(self) -> str:
        return str(self._handle.info_hash())

    def get_status(self) -> TorrentStatus:
        s = self._handle.status()
        state_str = _STATE_MAP.get(s.state, str(s.state))
        total = s.total_wanted if s.total_wanted > 0 else 0
        downloaded = int(total * s.progress)
        error = s.errc.message() if s.errc.value() != 0 else ""
        return TorrentStatus(
            info_hash=str(s.info_hash),
            name=s.name,
            state=state_str,
            progress=s.progress,
            download_rate=s.download_rate,
            upload_rate=s.upload_rate,
            num_peers=s.num_peers,
            total_size=total,
            downloaded=downloaded,
            save_path=s.save_path,
            error=error,
        )

    def is_complete(self) -> bool:
        s = self._handle.status()
        return s.state in (lt.torrent_status.finished, lt.torrent_status.seeding)

    def raw_handle(self) -> lt.torrent_handle:
        return self._handle
