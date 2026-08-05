from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from torrent.manager import TorrentManager
from api.routes import router, set_manager

manager = TorrentManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    set_manager(manager)
    manager.start()
    yield
    manager.stop()


app = FastAPI(title="PyTorrent", lifespan=lifespan)
app.include_router(router)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
