"""Desktop entry point: runs the server and opens the UI in a browser."""

import multiprocessing
import os
import socket
import threading
import time
import webbrowser

import uvicorn

HOST = os.environ.get("PYTORRENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("PYTORRENT_PORT", "8765"))


def _pick_port(host: str, preferred: int) -> int:
    # A WSL2 dev server on the same port gets forwarded to Windows localhost,
    # so the preferred port being taken is a realistic double-click scenario.
    with socket.socket() as s:
        try:
            s.bind((host, preferred))
            return preferred
        except OSError:
            pass
    with socket.socket() as s:
        s.bind((host, 0))
        port = s.getsockname()[1]
    print(f"Port {preferred} is already in use; using {port} instead", flush=True)
    return port


def _open_browser_when_ready(server: uvicorn.Server, url: str) -> None:
    # Waiting on server.started means we never open a tab for a server that
    # failed to bind.
    while not server.started:
        time.sleep(0.1)
    webbrowser.open(url)


def main() -> None:
    from main import app

    if HOST not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("PYTORRENT_PASSWORD"):
        print(
            f"WARNING: listening on {HOST} without PYTORRENT_PASSWORD set - anyone on "
            "your network can control PyTorrent.",
            flush=True,
        )

    port = _pick_port(HOST, PORT)
    url = f"http://{HOST}:{port}/"
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, log_level="info"))

    if not os.environ.get("PYTORRENT_NO_BROWSER"):
        threading.Thread(
            target=_open_browser_when_ready, args=(server, url), daemon=True
        ).start()

    print(f"PyTorrent starting at {url} (Ctrl+C to stop)", flush=True)
    try:
        server.run()
    except KeyboardInterrupt:
        # uvicorn re-raises after its own graceful shutdown; no traceback needed
        pass
    print("PyTorrent stopped.")
    if not server.started:
        # Double-clicked console windows close on exit; hold them open so the
        # error above stays readable.
        input("Startup failed - press Enter to close...")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        input("Unexpected error - press Enter to close...")
