# PyTorrent

A lightweight BitTorrent client with a web UI, built on top of [libtorrent](https://www.libtorrent.org/).

## Features

- Add and manage torrents via a web interface
- Real-time torrent status updates using Server-Sent Events (SSE)
- Cross-platform support (Windows, Linux, macOS)
- Packaged as a standalone Windows executable

## Installation

### From Source

Requires Python 3.11+.

```bash
# Clone the repository
git clone https://github.com/Ledu55/pytorrent.git
cd pytorrent

# Install dependencies
uv sync

# Run the application
uv run python -m uvicorn main:app --reload
```

The application will start at `http://127.0.0.1:8000` by default.

### Windows Executable

Pre-built Windows executables are available on the [releases page](https://github.com/Ledu55/pytorrent/releases).

## Configuration

### Download Directory

By default, downloaded torrents are saved to `~/Downloads/pytorrent`. You can override this with the `PYTORRENT_DOWNLOAD_ROOT` environment variable:

```bash
export PYTORRENT_DOWNLOAD_ROOT=/path/to/downloads
uv run python -m uvicorn main:app
```

## API Endpoints

- `GET /api/config` — Get current configuration
- `GET /api/torrents` — List all torrents
- `POST /api/torrents` — Add a new torrent (upload `.torrent` file)
- `DELETE /api/torrents/{info_hash}` — Remove a torrent
- `GET /api/events` — Server-Sent Events stream for real-time updates

## Development

### Running Tests

```bash
uv sync --all-groups
uv run pytest tests/ -v
```

### Linting

```bash
uv sync --all-groups
uv run ruff check .
```

## License

This project is provided as-is for educational and personal use.
