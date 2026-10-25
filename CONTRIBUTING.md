# Contributing

Thanks for wanting to help! Bug reports, ideas and pull requests are all welcome.

## Setup

```bash
git clone https://github.com/Ledu55/pytorrent.git
cd pytorrent
uv sync --all-groups
uv run pytorrent
```

The UI is plain HTML/CSS/JS in `static/`. There's no build step, so refresh the
browser to see your changes. For backend changes, run uvicorn with reload:

```bash
uv run uvicorn main:app --reload --port 8765
```

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the pieces fit together.

## Before opening a PR

```bash
uv run ruff check .
uv run pytest tests/ -v
```

- Keep PRs focused on one thing.
- Add or update tests for backend changes.
- For UI changes, include a screenshot and check both light and dark themes and
  a narrow (phone-sized) window.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `chore:` …). The release workflow uses them to pick the next version.

## Reporting bugs

Please attach the log file. It's in your config folder:

- Windows: `%APPDATA%\pytorrent\pytorrent.log`
- macOS: `~/Library/Application Support/pytorrent/pytorrent.log`
- Linux: `~/.config/pytorrent/pytorrent.log`
