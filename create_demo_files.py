#!/usr/bin/env python3
"""Generate a safe demo file tree for README screenshots and local testing."""

from __future__ import annotations

import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEMO_ROOT = PROJECT_ROOT / "demo_files"

TEXT_FILES: dict[str, str] = {
    "Projects/App_Demo/project_notes.txt": """\
Local Resource Manager — demo project notes

- Multi-column folder navigation
- Fast indexed search by file name or extension
- Bookmark tabs for repeat workflows

This folder is synthetic demo content for screenshots only.
""",
    "Projects/App_Demo/README.md": """\
# App Demo

Placeholder project used to demonstrate folder browsing and search.
No real user data is included.
""",
    "Projects/Research/experiment_data.csv": """\
sample_id,condition,result_ms,notes
A-001,baseline,142,control run
A-002,variant,128,second trial
B-001,baseline,151,repeat measurement
""",
    "Projects/Research/lab_notes.txt": """\
Research demo notes

Use this folder to show subtree search and folder match counts.
All names and values here are fictional.
""",
    "Documents/project_notes.txt": """\
Documents demo file.

Try searching for: report, presentation, notes
""",
    "Documents/README.md": """\
# Documents

Synthetic documents folder for public screenshots.
""",
    "Data/metrics_export.csv": """\
date,indexed_files,search_ms
2026-01-10,1200,18
2026-01-11,1248,16
2026-01-12,1302,15
""",
    "Data/readme.txt": """\
Data folder demo.

Useful for showing mixed file types in the file list panel.
""",
    "Archive/readme.txt": """\
Archive demo folder.

Contains a placeholder zip file name for extension-based search.
""",
    "Photos/readme.txt": """\
Photos demo folder.

Add screenshot captures here after you take them, if desired.
""",
}

EMPTY_FILES = [
    "Projects/App_Demo/design_mockup.png",
    "Projects/Research/sample_report_2026.pdf",
    "Documents/presentation_draft.pptx",
    "Photos/photo_collection.jpg",
    "Archive/archive_backup.zip",
]


def create_demo_files(root: Path = DEMO_ROOT) -> None:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    for relative_path, content in TEXT_FILES.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")

    for relative_path in EMPTY_FILES:
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"")

    print(f"Created demo file tree at: {root}")
    print(f"Folders: {sum(1 for path in root.rglob('*') if path.is_dir())}")
    print(f"Files:   {sum(1 for path in root.rglob('*') if path.is_file())}")
    print()
    print("In Local Resource Manager: Select Root Folder -> choose demo_files")


if __name__ == "__main__":
    create_demo_files()
