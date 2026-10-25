"""Tests for api/routes.py."""

import base64

import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.auth import PasswordMiddleware
from api.routes import router, set_manager
from torrent.config import Settings
from torrent.manager import DuplicateTorrentError, TorrentManager
from torrent.handle import TorrentStatus


@pytest.fixture
def download_root(tmp_path):
    root = tmp_path / "downloads"
    root.mkdir()
    return root.resolve()


@pytest.fixture
def manager(download_root):
    m = MagicMock(spec=TorrentManager)
    m.settings = Settings(download_root=str(download_root))
    set_manager(m)
    return m


@pytest.fixture
def client():
    """Create a test client with the router mounted."""
    test_app = FastAPI()
    test_app.include_router(router)
    return TestClient(test_app)


def _status(**overrides) -> TorrentStatus:
    base = dict(
        info_hash="test_hash",
        name="test.torrent",
        state="downloading",
        progress=0.5,
        download_rate=1000,
        upload_rate=500,
        num_peers=10,
        total_size=5000,
        downloaded=2500,
        save_path="/tmp/test",
        error="",
    )
    base.update(overrides)
    return TorrentStatus(**base)


def test_get_config(client, manager, download_root):
    response = client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    assert body["download_root"] == str(download_root)
    assert body["free_space"] > 0


def test_add_torrent_success(client, manager):
    manager.add_torrent.return_value = "test_info_hash"
    files = {"file": ("test.torrent", b"fake torrent data")}

    response = client.post("/api/torrents", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["info_hash"] == "test_info_hash"
    assert data["message"] == "Torrent added"


def test_add_torrent_wrong_extension(client, manager):
    files = {"file": ("test.txt", b"not a torrent")}
    response = client.post("/api/torrents", files=files)
    assert response.status_code == 400
    assert "Only .torrent files" in response.json()["detail"]


def test_add_torrent_too_large(client, manager):
    large_data = b"x" * (11 * 1024 * 1024)
    files = {"file": ("large.torrent", large_data)}

    response = client.post("/api/torrents", files=files)
    assert response.status_code == 413
    assert "too large" in response.json()["detail"]


def test_add_torrent_invalid(client, manager):
    manager.add_torrent.side_effect = RuntimeError("bad bencode")
    files = {"file": ("broken.torrent", b"junk")}
    response = client.post("/api/torrents", files=files)
    assert response.status_code == 422
    assert "broken.torrent" in response.json()["detail"]


def test_add_torrent_duplicate(client, manager):
    manager.add_torrent.side_effect = DuplicateTorrentError("h")
    files = {"file": ("a.torrent", b"data")}
    response = client.post("/api/torrents", files=files)
    assert response.status_code == 409


def test_add_torrent_path_traversal_rejected(client, manager):
    files = {"file": ("test.torrent", b"fake data")}
    response = client.post("/api/torrents", files=files, data={"save_path": "../../etc"})
    assert response.status_code == 400
    assert "must be inside" in response.json()["detail"]


def test_add_torrent_relative_subfolder_accepted(client, manager, download_root):
    manager.add_torrent.return_value = "test_hash"
    files = {"file": ("test.torrent", b"fake data")}

    response = client.post("/api/torrents", files=files, data={"save_path": "movies"})

    assert response.status_code == 200
    assert manager.add_torrent.call_args.args[1] == str(download_root / "movies")
    assert (download_root / "movies").is_dir()


def test_add_magnet(client, manager):
    manager.add_magnet.return_value = "mag_hash"
    response = client.post(
        "/api/torrents/magnet", json={"uri": "magnet:?xt=urn:btih:" + "a" * 40}
    )
    assert response.status_code == 200
    assert response.json()["info_hash"] == "mag_hash"


def test_add_magnet_rejects_non_magnet(client, manager):
    response = client.post("/api/torrents/magnet", json={"uri": "http://example.com"})
    assert response.status_code == 400
    manager.add_magnet.assert_not_called()


def test_list_torrents(client, manager):
    manager.get_all_statuses.return_value = [_status()]

    response = client.get("/api/torrents")

    assert response.status_code == 200
    torrents = response.json()
    assert len(torrents) == 1
    assert torrents[0]["info_hash"] == "test_hash"
    assert torrents[0]["progress"] == 0.5


def test_remove_torrent_success(client, manager):
    manager.remove_torrent.return_value = True
    response = client.delete("/api/torrents/test_hash")
    assert response.status_code == 200
    manager.remove_torrent.assert_called_once_with("test_hash", False)


def test_remove_torrent_with_files(client, manager):
    manager.remove_torrent.return_value = True
    response = client.delete("/api/torrents/test_hash?delete_files=true")
    assert response.status_code == 200
    manager.remove_torrent.assert_called_once_with("test_hash", True)


def test_remove_torrent_not_found(client, manager):
    manager.remove_torrent.return_value = False
    response = client.delete("/api/torrents/nonexistent_hash")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@pytest.mark.parametrize("action", ["pause", "resume", "recheck", "reannounce"])
def test_torrent_actions(client, manager, action):
    response = client.post(f"/api/torrents/abc/{action}")
    assert response.status_code == 200
    getattr(manager, action).assert_called_once_with("abc")


def test_torrent_action_unknown_torrent(client, manager):
    manager.pause.side_effect = KeyError("abc")
    assert client.post("/api/torrents/abc/pause").status_code == 404


def test_torrent_action_unknown_action(client, manager):
    assert client.post("/api/torrents/abc/explode").status_code == 404


def test_pause_resume_all(client, manager):
    assert client.post("/api/torrents/pause-all").status_code == 200
    assert client.post("/api/torrents/resume-all").status_code == 200
    manager.pause_all.assert_called_once()
    manager.resume_all.assert_called_once()


def test_set_file_priorities(client, manager):
    response = client.put("/api/torrents/abc/files", json={"0": 0, "2": 9})
    assert response.status_code == 200
    # Out-of-range priorities are clamped to libtorrent's 0..7
    manager.set_file_priorities.assert_called_once_with("abc", {0: 0, 2: 7})


def test_settings_roundtrip(client, manager, tmp_path):
    response = client.put("/api/settings", json={"listen_port": "7000", "upload_limit_kbps": 50})
    assert response.status_code == 200
    assert response.json()["listen_port"] == 7000
    applied = manager.apply_settings.call_args.args[0]
    assert applied.upload_limit_kbps == 50
    assert (tmp_path / "config" / "settings.json").exists()


def test_settings_validation(client, manager):
    response = client.put("/api/settings", json={"listen_port": 70000})
    assert response.status_code == 400
    manager.apply_settings.assert_not_called()


def test_password_middleware(manager):
    app = FastAPI()
    app.add_middleware(PasswordMiddleware, password="s3cret")
    app.include_router(router)
    c = TestClient(app)

    assert c.get("/api/torrents").status_code == 401
    bad = base64.b64encode(b"user:nope").decode()
    assert c.get("/api/torrents", headers={"Authorization": f"Basic {bad}"}).status_code == 401
    good = base64.b64encode(b"anyone:s3cret").decode()
    manager.get_all_statuses.return_value = []
    assert c.get("/api/torrents", headers={"Authorization": f"Basic {good}"}).status_code == 200
