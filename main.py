import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from torrent.manager import TorrentManager
from api.routes import router, set_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

def _resource_path(name: str) -> Path:
    # sys._MEIPASS is where PyInstaller unpacks bundled data files
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


manager = TorrentManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    set_manager(manager)
    manager.start()
    yield
    manager.stop()


app = FastAPI(title="PyTorrent", lifespan=lifespan)
app.include_router(router)
app.mount(
    "/",
    StaticFiles(directory=str(_resource_path("static")), html=True),
    name="static",
)
