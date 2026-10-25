FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev

ENV PYTORRENT_HOST=0.0.0.0 \
    PYTORRENT_PORT=8765 \
    PYTORRENT_NO_BROWSER=1 \
    PYTORRENT_CONFIG_DIR=/config \
    PYTORRENT_DOWNLOAD_ROOT=/downloads

VOLUME ["/config", "/downloads"]
# 8765 = web UI, 6999 = BitTorrent peers
EXPOSE 8765 6999/tcp 6999/udp

CMD ["uv", "run", "--no-sync", "pytorrent"]
