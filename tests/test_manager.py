"""Tests for torrent/manager.py."""

import asyncio
from unittest.mock import MagicMock, patch
import pytest
from torrent.manager import TorrentManager
from torrent.handle import TorrentStatus
import libtorrent as lt


def test_add_torrent():
    """Test adding a torrent populates handles and statuses."""
    manager = TorrentManager()

    # Mock the session and handle
    mock_handle = MagicMock()
    mock_handle.info_hash.return_value = "test_hash_123"
    mock_handle.status.return_value = MagicMock(
        info_hash="test_hash_123",
        name="test.torrent",
        state=lt.torrent_status.downloading,
        progress=0.0,
        total_wanted=1000,
        download_rate=0,
        upload_rate=0,
        num_peers=0,
        save_path="/tmp/test",
        errc=MagicMock(value=lambda: 0, message=lambda: ""),
    )

    with patch("torrent.manager.lt.torrent_info") as mock_torrent_info:
        mock_torrent_info.return_value = MagicMock()
        with patch.object(manager._session, "add_torrent", return_value=mock_handle):
            info_hash = manager.add_torrent(b"fake_torrent_data", "/tmp/test")

    assert info_hash == "test_hash_123"
    assert info_hash in manager._handles
    assert info_hash in manager._statuses


def test_remove_torrent_success():
    """Test removing an existing torrent."""
    manager = TorrentManager()

    # Setup a torrent
    mock_handle = MagicMock()
    mock_handle.info_hash.return_value = "test_hash_123"
    mock_handle.status.return_value = MagicMock(
        info_hash="test_hash_123",
        name="test.torrent",
        state=lt.torrent_status.downloading,
        progress=0.0,
        total_wanted=1000,
        download_rate=0,
        upload_rate=0,
        num_peers=0,
        save_path="/tmp/test",
        errc=MagicMock(value=lambda: 0, message=lambda: ""),
    )

    with patch("torrent.manager.lt.torrent_info") as mock_torrent_info:
        mock_torrent_info.return_value = MagicMock()
        with patch.object(manager._session, "add_torrent", return_value=mock_handle):
            manager.add_torrent(b"fake_torrent_data", "/tmp/test")

    # Remove it, patching remove_torrent to avoid calling libtorrent
    with patch.object(manager._session, "remove_torrent"):
        result = manager.remove_torrent("test_hash_123")

    assert result is True
    assert "test_hash_123" not in manager._handles
    assert "test_hash_123" not in manager._statuses


def test_remove_torrent_not_found():
    """Test removing a non-existent torrent returns False."""
    manager = TorrentManager()
    result = manager.remove_torrent("nonexistent_hash")
    assert result is False


def test_subscribe_unsubscribe():
    """Test subscribing and unsubscribing."""
    manager = TorrentManager()

    q = manager.subscribe()
    assert q in manager._subscribers

    manager.unsubscribe(q)
    assert q not in manager._subscribers


def test_unsubscribe_not_found():
    """Test unsubscribing a queue that was never subscribed."""
    manager = TorrentManager()
    q = asyncio.Queue()
    # Should not raise
    manager.unsubscribe(q)


@pytest.mark.asyncio
async def test_broadcast_backpressure():
    """Test that slow consumers have old frames dropped."""
    manager = TorrentManager()

    # Create a queue with maxsize=2
    q = asyncio.Queue(maxsize=2)
    manager._subscribers.append(q)

    # Create some test statuses
    status1 = TorrentStatus(
        info_hash="h1",
        name="test1",
        state="downloading",
        progress=0.1,
        download_rate=100,
        upload_rate=10,
        num_peers=5,
        total_size=1000,
        downloaded=100,
        save_path="/tmp",
        error="",
    )
    status2 = TorrentStatus(
        info_hash="h2",
        name="test2",
        state="downloading",
        progress=0.2,
        download_rate=200,
        upload_rate=20,
        num_peers=10,
        total_size=2000,
        downloaded=400,
        save_path="/tmp",
        error="",
    )
    status3 = TorrentStatus(
        info_hash="h3",
        name="test3",
        state="downloading",
        progress=0.3,
        download_rate=300,
        upload_rate=30,
        num_peers=15,
        total_size=3000,
        downloaded=900,
        save_path="/tmp",
        error="",
    )

    # Fill queue to maxsize with first two statuses
    manager._broadcast([status1])
    manager._broadcast([status2])

    # Queue is now full. Broadcasting a third should drop the oldest (status1)
    manager._broadcast([status3])

    # Verify queue still has 2 items and the newest is status3
    assert q.qsize() == 2
    frame2 = await q.get()
    frame3 = await q.get()
    # frame2 should be status2, frame3 should be status3
    assert frame2[0]["info_hash"] == "h2"
    assert frame3[0]["info_hash"] == "h3"
