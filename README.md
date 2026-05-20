# Local Resource Manager

A desktop **file explorer and lightweight indexer**: pick a root folder, scan it into an in-memory index, browse with a multi-column outline, filter by folder tree, search by filename or extension, and inspect files in a table with themes and configurable shortcuts.

**Repository:** [github.com/xintian-lab/local-resource-manager](https://github.com/xintian-lab/local-resource-manager)

## Requirements

- **Python** 3.10+ recommended
- **Windows** — current primary dev and test target (macOS support is planned for packaged builds).

## Virtual environment (local only)

The `.venv` folder is **only for the computer where you create it**. It contains OS-specific binaries and must **not** be shared between machines via Git, Dropbox, OneDrive, iCloud Drive, or similar sync tools. Sharing it causes broken installs, huge uploads, and overwritten environments.

**Do this on each machine:**

1. Open your cloud sync settings for this project folder and **exclude** `.venv` from sync (and optionally any alternate names like `venv/` if you use them).
2. Create the environment locally (commands below), then run `pip install -r requirements.txt`.

The repo already lists `.venv/` in `.gitignore` so it never gets committed.

## Quick start

```bash
cd local-resource-manager
```

**Windows (PowerShell or Command Prompt):**

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

**Cursor / VS Code:** open the project folder; the Python extension should detect `.venv` automatically. Use **Python: Select Interpreter** if needed and pick `.venv` → `python`. Integrated terminals can auto-activate the venv when `python.terminal.activateEnvironment` is enabled (set in `.vscode/settings.json`).

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
