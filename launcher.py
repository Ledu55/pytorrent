"""Desktop entry point: runs the server and opens the UI in a browser."""

import multiprocessing
import os
import threading
import time
import webbrowser

import uvicorn

HOST = os.environ.get("PYTORRENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("PYTORRENT_PORT", "8765"))
URL = f"http://{HOST}:{PORT}/"


def _open_browser_when_ready(server: uvicorn.Server) -> None:
    # Waiting on server.started means we never open a tab for a server that
    # failed to bind.
    while not server.started:
        time.sleep(0.1)
    webbrowser.open(URL)


def main() -> None:
    from main import app

    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="info"))

    if not os.environ.get("PYTORRENT_NO_BROWSER"):
        threading.Thread(
            target=_open_browser_when_ready, args=(server,), daemon=True
        ).start()

    print(f"PyTorrent starting at {URL} (Ctrl+C to stop)")
    try:
        server.run()
    except KeyboardInterrupt:
        # uvicorn re-raises after its own graceful shutdown; no traceback needed
        pass
    print("PyTorrent stopped.")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
