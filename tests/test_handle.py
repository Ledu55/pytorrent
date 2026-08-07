"""Tests for torrent/handle.py."""

from types import SimpleNamespace
from torrent.handle import status_from_lt


class FakeError:
    """Fake libtorrent error code."""

    def __init__(self, value: int = 0):
        self._value = value

    def value(self) -> int:
        return self._value

    def message(self) -> str:
        if self._value == 0:
            return ""
        return f"Error {self._value}"


def test_status_from_lt_basic():
    """Test basic status mapping."""
    import libtorrent as lt

    fake_status = SimpleNamespace(
        info_hash="abc123def456",
        name="test.torrent",
        state=lt.torrent_status.downloading,
        progress=0.5,
        total_wanted=1000,
        download_rate=100,
        upload_rate=50,
        num_peers=5,
        save_path="/tmp/test",
        errc=FakeError(0),
    )

    result = status_from_lt(fake_status)

    assert result.info_hash == "abc123def456"
    assert result.name == "test.torrent"
    assert result.state == "downloading"
    assert result.progress == 0.5
    assert result.download_rate == 100
    assert result.upload_rate == 50
    assert result.num_peers == 5
    assert result.total_size == 1000
    assert result.downloaded == 500
    assert result.save_path == "/tmp/test"
    assert result.error == ""


def test_status_from_lt_with_error():
    """Test status mapping with error."""
    import libtorrent as lt

    fake_status = SimpleNamespace(
        info_hash="xyz789",
        name="error.torrent",
        state=lt.torrent_status.checking_files,
        progress=0.0,
        total_wanted=0,
        download_rate=0,
        upload_rate=0,
        num_peers=0,
        save_path="/tmp",
        errc=FakeError(1),
    )

    result = status_from_lt(fake_status)

    assert result.error == "Error 1"
    assert result.total_size == 0
    assert result.downloaded == 0


def test_status_from_lt_state_mapping():
    """Test all state mappings."""
    import libtorrent as lt

    states = [
        (lt.torrent_status.checking_files, "checking"),
        (lt.torrent_status.downloading_metadata, "downloading metadata"),
        (lt.torrent_status.downloading, "downloading"),
        (lt.torrent_status.finished, "finished"),
        (lt.torrent_status.seeding, "seeding"),
        (lt.torrent_status.checking_resume_data, "checking resume"),
    ]

    for lt_state, expected_str in states:
        fake_status = SimpleNamespace(
            info_hash="test",
            name="test",
            state=lt_state,
            progress=0.0,
            total_wanted=0,
            download_rate=0,
            upload_rate=0,
            num_peers=0,
            save_path="/tmp",
            errc=FakeError(0),
        )
        result = status_from_lt(fake_status)
        assert result.state == expected_str


def test_status_from_lt_downloaded_calc():
    """Test downloaded bytes calculation from progress."""
    import libtorrent as lt

    fake_status = SimpleNamespace(
        info_hash="test",
        name="test",
        state=lt.torrent_status.downloading,
        progress=0.75,
        total_wanted=10000,
        download_rate=0,
        upload_rate=0,
        num_peers=0,
        save_path="/tmp",
        errc=FakeError(0),
    )

    result = status_from_lt(fake_status)
    assert result.total_size == 10000
    assert result.downloaded == 7500
