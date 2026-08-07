import libtorrent as lt


class TorrentSession:
    """Wraps lt.session with standard peer settings."""

    def __init__(self) -> None:
        settings = {
            "listen_interfaces": "0.0.0.0:6999",
            "alert_mask": lt.alert.category_t.all_categories,
        }
        self._session = lt.session(settings)
        self._session.add_dht_router("router.bittorrent.com", 6881)
        self._session.add_dht_router("router.utorrent.com", 6881)
        self._session.add_dht_router("dht.transmissionbt.com", 6881)

    def add_torrent(self, torrent_info: lt.torrent_info, save_path: str) -> lt.torrent_handle:
        params = {
            "ti": torrent_info,
            "save_path": save_path,
        }
        return self._session.add_torrent(params)

    def remove_torrent(self, handle: lt.torrent_handle) -> None:
        self._session.remove_torrent(handle)

    def post_torrent_updates(self) -> None:
        self._session.post_torrent_updates()

    def pop_alerts(self) -> list:
        return self._session.pop_alerts()

    def pause(self) -> None:
        self._session.pause()
