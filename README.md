# PyTorrent

A lightweight, open-source BitTorrent client with a clean web UI, built on
[libtorrent](https://www.libtorrent.org/). Run it on your desktop, or on a
home server and use it from your phone.

<!-- Add a screenshot: docs/screenshot.png -->

## Features

- **Add torrents your way**: drag & drop `.torrent` files anywhere on the page, paste a magnet link, or use the Add dialog (several at once)
- **Picks up where it left off**: torrents and their progress are restored after a restart
- **Full control**: pause or resume (one torrent or all), remove with or without deleting the files, verify files, find more peers
- **Pick what to download**: choose which files to download inside a torrent and set their priority
- **Detail panel** with files, peers and trackers
- **Filters, search and sorting**, and live speed totals in the status bar and browser tab title
- **Settings**: download folder, speed limits, queue size, stop seeding at a ratio, listen port, automatic router port forwarding (UPnP / NAT-PMP)
- **Light and dark themes**, phone-friendly layout, keyboard shortcuts
- **Notifications** when a download finishes
- **Optional password** for remote access
- Runs on Windows, macOS and Linux, from source, as a standalone build, or in Docker

## Quick start

### Download a build

Get the latest Windows, macOS or Linux build from the
[releases page](https://github.com/Ledu55/pytorrent/releases), unzip it, and
run `pytorrent`. Your browser opens the UI automatically.

> The builds aren't code-signed. On Windows, SmartScreen may warn you: click
> **More info → Run anyway**. On macOS, right-click the app and choose **Open**
> the first time.

### Run from source

Requires Python 3.11–3.13 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Ledu55/pytorrent.git
cd pytorrent
uv sync
uv run pytorrent
```

### Docker

```bash
docker build -t pytorrent .
docker run -d --name pytorrent \
  -p 8765:8765 -p 6999:6999 -p 6999:6999/udp \
  -e PYTORRENT_PASSWORD=change-me \
  -v ./config:/config -v ./downloads:/downloads \
  pytorrent
```

Open `http://<host>:8765` and log in with any username and your password.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| <kbd>N</kbd> | Add torrent |
| <kbd>/</kbd> | Search |
| <kbd>↑</kbd> / <kbd>↓</kbd> | Move selection |
| <kbd>Space</kbd> | Pause / resume selected |
| <kbd>Del</kbd> | Remove selected |
| <kbd>Esc</kbd> | Close panel or dialog |

You can also paste a magnet link anywhere on the page.

## Configuration

Most options are in the **Settings** dialog and are saved to `settings.json`
in your config folder. These environment variables control startup:

| Variable | Default | Description |
| --- | --- | --- |
| `PYTORRENT_HOST` | `127.0.0.1` | Address the web UI listens on. Use `0.0.0.0` to allow other devices (set a password!). |
| `PYTORRENT_PORT` | `8765` | Web UI port. Falls back to a free port if taken. |
| `PYTORRENT_PASSWORD` | *(unset)* | Enables password protection (any username). |
| `PYTORRENT_DOWNLOAD_ROOT` | `~/Downloads/pytorrent` | Default download folder before you change it in Settings. |
| `PYTORRENT_CONFIG_DIR` | see below | Where settings, resume data and logs are stored. |
| `PYTORRENT_NO_BROWSER` | *(unset)* | Don't open a browser on start. |

Config folder: `%APPDATA%\pytorrent` (Windows), `~/Library/Application Support/pytorrent` (macOS), `~/.config/pytorrent` (Linux).

## Troubleshooting

- **No peers / slow downloads.** The status bar shows whether PyTorrent is listening. Allow PyTorrent through your firewall, and either keep *UPnP* enabled in Settings or forward the listen port (default `6999`, TCP + UDP) on your router.
- **"The save folder must be inside your download folder".** Subfolders are relative to the download folder. To save somewhere else, change the download folder in Settings.
- **The browser didn't open.** Go to the address printed in the console (default `http://127.0.0.1:8765`).
- **Something else.** Check `pytorrent.log` in the config folder and [open an issue](https://github.com/Ledu55/pytorrent/issues) with it attached.

## API

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/torrents` | List torrents |
| `POST` | `/api/torrents` | Add a `.torrent` file (multipart `file`, optional `save_path`) |
| `POST` | `/api/torrents/magnet` | Add a magnet link (`{"uri": "...", "save_path": null}`) |
| `DELETE` | `/api/torrents/{hash}?delete_files=false` | Remove a torrent |
| `POST` | `/api/torrents/{hash}/{pause\|resume\|recheck\|reannounce\|open}` | Torrent actions |
| `POST` | `/api/torrents/pause-all`, `/api/torrents/resume-all` | Bulk pause / resume |
| `GET` | `/api/torrents/{hash}/details` | Files, peers and trackers |
| `PUT` | `/api/torrents/{hash}/files` | Set file priorities (`{"0": 0, "1": 7}`) |
| `GET`/`PUT` | `/api/settings` | Read / update settings |
| `GET` | `/api/config`, `/api/session` | Download folder, free space, listen status |
| `GET` | `/api/events` | Server-Sent Events stream of status updates |

Interactive docs are at `/docs` while the app is running.

## Development

```bash
uv sync --all-groups
uv run pytest tests/ -v
uv run ruff check .
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License

[MIT](LICENSE). Use PyTorrent only for content you have the right to download and share.
