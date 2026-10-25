import pytest


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    # Keep tests away from the real per-user settings and resume data
    monkeypatch.setenv("PYTORRENT_CONFIG_DIR", str(tmp_path / "config"))
