# Local Resource Manager

A desktop **file explorer and lightweight indexer**: pick a root folder, scan it into an in-memory index, browse with a multi-column outline, filter by folder tree, search by filename or extension, and inspect files in a table with themes and configurable shortcuts.

**Repository:** [github.com/xintian-lab/local-resource-manager](https://github.com/xintian-lab/local-resource-manager)

## Requirements

- **Python** 3.10+ recommended
- **Windows** — current primary dev and test target (macOS support is planned for packaged builds).

## Quick start

```bash
cd local-resource-manager
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux / macOS:
# source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Dependencies

See [`requirements.txt`](requirements.txt): **PySide6** drives the GUI; **PyInstaller** is included for future packaging workflows.

## Data and configuration (local paths)

Running from source uses paths under your project/checkout:

| Purpose | Location |
| -------- | --------- |
| SQLite index | `app/data/file_index.db` (ignored by Git) |
| User settings (theme, shortcuts, etc.) | `app/config/settings.json` (ignored by Git) |

After cloning, files are created on first run. **Do not commit** a `settings.json` that contains private paths.

## Repository layout

```
main.py           # Entry point
app/ui/           # PySide widgets (main window, column browser, file table)
app/core/         # Scanner, indexer, search, paths, file operations
build_exe.ps1     # Windows-oriented build helper (evolving)
```

## Roadmap

Planned additions (will land in-repo and ship via **`git push` / Releases**):

- **Windows** — downloadable **`.exe`** (or installer) built with PyInstaller (or similar), with sensible signing and versioning TBD.
- **macOS** — **`.app`** bundle distribution (same Qt stack via PyInstaller or platform-specific tooling), notarized/signing workflow TBD.
- Smaller fixes: portability checks on macOS, CI to build binaries in a repeatable way once the pipelines are settled.

Contribution and issue tracking welcome as the packaged releases stabilize.

## License

Not stated yet — a `LICENSE` file will be added when the redistribution terms are finalized.
