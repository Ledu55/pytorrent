"""User settings and per-user data locations."""

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

logger = logging.getLogger(__name__)


def config_dir() -> Path:
    """Per-user directory for settings, resume data and logs."""
    override = os.environ.get("PYTORRENT_CONFIG_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "pytorrent"


def resume_dir() -> Path:
    return config_dir() / "resume"


def log_path() -> Path:
    return config_dir() / "pytorrent.log"


def default_download_root() -> str:
    return os.environ.get(
        "PYTORRENT_DOWNLOAD_ROOT", str(Path.home() / "Downloads" / "pytorrent")
    )


@dataclass
class Settings:
    download_root: str = ""
    listen_port: int = 6999
    download_limit_kbps: int = 0  # 0 = unlimited
    upload_limit_kbps: int = 0
    active_downloads: int = 3
    active_seeds: int = 5
    seed_ratio_limit: float = 0.0  # 0 = seed forever
    enable_upnp: bool = True

    def __post_init__(self) -> None:
        if not self.download_root:
            self.download_root = default_download_root()

    def validate(self) -> None:
        if not 1 <= self.listen_port <= 65535:
            raise ValueError("Listen port must be between 1 and 65535")
        for name in ("download_limit_kbps", "upload_limit_kbps"):
            if getattr(self, name) < 0:
                raise ValueError("Speed limits can't be negative")
        if self.active_downloads < 1 or self.active_seeds < 1:
            raise ValueError("Active download/seed counts must be at least 1")
        if self.seed_ratio_limit < 0:
            raise ValueError("Seed ratio limit can't be negative")
        if not self.download_root.strip():
            raise ValueError("Download folder can't be empty")


def _settings_file() -> Path:
    return config_dir() / "settings.json"


def load_settings() -> Settings:
    path = _settings_file()
    if not path.exists():
        return Settings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        known = {f.name for f in fields(Settings)}
        settings = Settings(**{k: v for k, v in raw.items() if k in known})
        settings.validate()
        return settings
    except Exception:
        logger.exception("Could not read %s; using defaults", path)
        return Settings()


def save_settings(settings: Settings) -> None:
    path = _settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    tmp.replace(path)
