import logging
import os
import sys
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.auth import PasswordMiddleware
from api.routes import router, set_manager
from torrent.config import load_settings, log_path, resume_dir
from torrent.manager import TorrentManager


def _setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        log_file = log_path()
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # The log is what people attach to bug reports, so keep it bounded
        handlers.append(
            RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
        )
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


_setup_logging()


def _resource_path(name: str) -> Path:
    # sys._MEIPASS is where PyInstaller unpacks bundled data files
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


manager = TorrentManager(load_settings(), resume_dir())


@asynccontextmanager
async def lifespan(app: FastAPI):
    set_manager(manager)
    try:
        manager.start()
    except Exception:
        logging.getLogger(__name__).exception("Failed to start torrent manager")
        raise
    yield
    manager.stop()


app = FastAPI(title="PyTorrent", lifespan=lifespan)

_password = os.environ.get("PYTORRENT_PASSWORD")
if _password:
    app.add_middleware(PasswordMiddleware, password=_password)

app.include_router(router)
app.mount(
    "/",
    StaticFiles(directory=str(_resource_path("static")), html=True),
    name="static",
)
