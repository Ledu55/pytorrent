import libtorrent as lt

from .config import Settings


class TorrentSession:
    """Wraps lt.session with standard peer settings."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._session = lt.session(
            {
                "alert_mask": lt.alert.category_t.status_notification
                | lt.alert.category_t.error_notification
                | lt.alert.category_t.storage_notification,
                "dht_bootstrap_nodes": "router.bittorrent.com:6881,"
                "router.utorrent.com:6881,dht.transmissionbt.com:6881",
            }
        )
        self.apply_settings(settings or Settings())

    def apply_settings(self, settings: Settings) -> None:
        self._session.apply_settings(
            {
                "listen_interfaces": f"0.0.0.0:{settings.listen_port},[::]:{settings.listen_port}",
                "download_rate_limit": settings.download_limit_kbps * 1024,
                "upload_rate_limit": settings.upload_limit_kbps * 1024,
                "active_downloads": settings.active_downloads,
                "active_seeds": settings.active_seeds,
                "active_limit": settings.active_downloads + settings.active_seeds,
                # libtorrent stores the ratio as a percentage; 0 disables the limit
                "share_ratio_limit": int(settings.seed_ratio_limit * 100),
                "enable_upnp": settings.enable_upnp,
                "enable_natpmp": settings.enable_upnp,
            }
        )

    def add_torrent(self, params: lt.add_torrent_params) -> lt.torrent_handle:
        return self._session.add_torrent(params)

    def remove_torrent(self, handle: lt.torrent_handle, delete_files: bool = False) -> None:
        flags = lt.session.delete_files if delete_files else 0
        self._session.remove_torrent(handle, flags)

    def post_torrent_updates(self) -> None:
        self._session.post_torrent_updates()

    def pop_alerts(self) -> list:
        return self._session.pop_alerts()

    def is_listening(self) -> bool:
        return self._session.is_listening()

    def listen_port(self) -> int:
        return self._session.listen_port()

    def dht_nodes(self) -> int:
        return self._session.status().dht_nodes

    def pause(self) -> None:
        self._session.pause()
