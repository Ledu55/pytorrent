# Architecture

PyTorrent is a single Python process: a FastAPI server that owns a libtorrent
session and serves a static web UI.

```
browser ──HTTP/SSE──▶ api/routes.py ──▶ torrent/manager.py ──▶ torrent/session.py ──▶ libtorrent
   ▲                                          │
   └──────────── /api/events (SSE) ◀──────────┘  poll thread, ~1 s
```

## Modules

| Path | Responsibility |
| --- | --- |
| `launcher.py` | Desktop entry point (`pytorrent` command / Windows exe). Picks a free port, starts uvicorn, opens the browser. |
| `main.py` | Builds the FastAPI app: logging, optional password middleware, manager lifecycle, static files. |
| `api/routes.py` | REST endpoints and the Server-Sent Events stream. Validates input and turns errors into readable messages. |
| `api/auth.py` | HTTP Basic auth, enabled only when `PYTORRENT_PASSWORD` is set. |
| `torrent/manager.py` | Owns all torrent handles. Runs a background poll thread that turns libtorrent alerts into status updates, saves resume data, and broadcasts updates to SSE subscribers. |
| `torrent/handle.py` | Thin wrapper around a libtorrent handle, plus `TorrentStatus` — the JSON shape the UI consumes. |
| `torrent/session.py` | Creates the libtorrent session and maps `Settings` onto libtorrent settings. |
| `torrent/config.py` | `Settings` dataclass, the per-user config directory, and settings load/save. |
| `static/` | The UI: plain HTML, CSS and JavaScript, no build step. |

## Threading

libtorrent does its work on its own threads. The manager's poll thread calls
`post_torrent_updates()` and `pop_alerts()` once a second. Status updates are
handed to the asyncio loop with `call_soon_threadsafe`, and each SSE client has
its own bounded queue; a slow client drops its oldest frame, not the connection.

## Persistence

Each torrent's resume data (including its metadata, so magnets don't need to
refetch it) is written to `<config dir>/resume/<info_hash>.fastresume`:

- right after a torrent is added, when metadata arrives, and when it finishes;
- every 30 seconds for torrents libtorrent marks as changed;
- for all torrents on clean shutdown.

On startup every `.fastresume` file is loaded back. Settings live in
`<config dir>/settings.json`.

| OS | Config dir |
| --- | --- |
| Windows | `%APPDATA%\pytorrent` |
| macOS | `~/Library/Application Support/pytorrent` |
| Linux | `$XDG_CONFIG_HOME/pytorrent` (default `~/.config/pytorrent`) |

## Security model

The server binds to `127.0.0.1` by default. All save paths must resolve inside
the configured download folder. Setting `PYTORRENT_PASSWORD` turns on HTTP
Basic auth for every route, which you should always do before binding to a
non-loopback address.
