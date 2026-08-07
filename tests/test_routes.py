"""Tests for api/routes.py."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routes import router, set_manager, DOWNLOAD_ROOT
from torrent.manager import TorrentManager
from torrent.handle import TorrentStatus


@pytest.fixture
def app():
    """Create a test app with the router mounted."""
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


def test_get_config(client):
    """Test GET /api/config returns download root."""
    manager = MagicMock(spec=TorrentManager)
    set_manager(manager)
    response = client.get("/api/config")
    assert response.status_code == 200
    assert "download_root" in response.json()


def test_add_torrent_success(client):
    """Test successfully adding a .torrent file."""
    manager = MagicMock(spec=TorrentManager)
    manager.add_torrent.return_value = "test_info_hash"
    set_manager(manager)

    # Create a fake .torrent file
    torrent_content = b"fake torrent data"
    files = {"file": ("test.torrent", torrent_content)}

    response = client.post("/api/torrents", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["info_hash"] == "test_info_hash"
    assert data["message"] == "Torrent added"


def test_add_torrent_wrong_extension(client):
    """Test that non-.torrent files are rejected."""
    manager = MagicMock(spec=TorrentManager)
    set_manager(manager)

    files = {"file": ("test.txt", b"not a torrent")}
    response = client.post("/api/torrents", files=files)
    assert response.status_code == 400
    assert "Only .torrent files" in response.json()["detail"]


def test_add_torrent_too_large(client):
    """Test that oversized torrent files are rejected."""
    manager = MagicMock(spec=TorrentManager)
    set_manager(manager)

    # 11 MB (larger than the 10 MB limit)
    large_data = b"x" * (11 * 1024 * 1024)
    files = {"file": ("large.torrent", large_data)}

    response = client.post("/api/torrents", files=files)
    assert response.status_code == 413
    assert "too large" in response.json()["detail"]


def test_add_torrent_path_traversal_rejected(client):
    """Test that path traversal outside DOWNLOAD_ROOT is rejected."""
    manager = MagicMock(spec=TorrentManager)
    set_manager(manager)

    # Try to save outside DOWNLOAD_ROOT
    files = {"file": ("test.torrent", b"fake data")}
    data = {"save_path": "/etc/passwd"}

    response = client.post("/api/torrents", files=files, data=data)
    assert response.status_code == 400
    assert "must be inside" in response.json()["detail"]


def test_add_torrent_path_inside_root_accepted(client):
    """Test that paths inside DOWNLOAD_ROOT are accepted."""
    manager = MagicMock(spec=TorrentManager)
    manager.add_torrent.return_value = "test_hash"
    set_manager(manager)

    # Create a subdirectory inside DOWNLOAD_ROOT
    subdir = DOWNLOAD_ROOT / "subdir"

    files = {"file": ("test.torrent", b"fake data")}
    data = {"save_path": str(subdir)}

    with patch("api.routes.Path.mkdir"):
        response = client.post("/api/torrents", files=files, data=data)

    assert response.status_code == 200


def test_list_torrents(client):
    """Test GET /api/torrents returns list of torrents."""
    status = TorrentStatus(
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

    manager = MagicMock(spec=TorrentManager)
    manager.get_all_statuses.return_value = [status]
    set_manager(manager)

    response = client.get("/api/torrents")

    assert response.status_code == 200
    torrents = response.json()
    assert len(torrents) == 1
    assert torrents[0]["info_hash"] == "test_hash"
    assert torrents[0]["name"] == "test.torrent"
    assert torrents[0]["progress"] == 0.5


def test_remove_torrent_success(client):
    """Test successfully removing a torrent."""
    manager = MagicMock(spec=TorrentManager)
    manager.remove_torrent.return_value = True
    set_manager(manager)

    response = client.delete("/api/torrents/test_hash")

    assert response.status_code == 200
    assert response.json()["message"] == "Removed"


def test_remove_torrent_not_found(client):
    """Test removing a non-existent torrent returns 404."""
    manager = MagicMock(spec=TorrentManager)
    manager.remove_torrent.return_value = False
    set_manager(manager)

    response = client.delete("/api/torrents/nonexistent_hash")

    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"]
