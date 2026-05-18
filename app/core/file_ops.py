from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

from app.core.scanner import FileRecord


def open_file(path: str | Path) -> None:
    target = Path(path)
    system = platform.system()

    if system == "Windows":
        os.startfile(target)  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


def open_containing_folder(path: str | Path) -> None:
    target = Path(path)
    folder = target if target.is_dir() else target.parent
    system = platform.system()

    if system == "Windows":
        if target.is_file():
            subprocess.Popen(["explorer", "/select,", str(target)])
        else:
            subprocess.Popen(["explorer", str(folder)])
    elif system == "Darwin":
        subprocess.Popen(["open", str(folder)])
    else:
        subprocess.Popen(["xdg-open", str(folder)])


def file_record_from_path(path: str | Path) -> FileRecord:
    target = Path(path).resolve()
    stat_result = target.stat()
    return FileRecord(
        name=target.name,
        path=str(target),
        folder_path=str(target.parent),
        extension=target.suffix.lower(),
        size=stat_result.st_size,
        modified_time=stat_result.st_mtime,
    )


def copy_file_to_folder(source_path: str | Path, destination_folder: str | Path) -> FileRecord:
    source = Path(source_path).resolve()
    destination = unique_destination(Path(destination_folder).resolve() / source.name)
    shutil.copy2(source, destination)
    return file_record_from_path(destination)


def move_file_to_folder(source_path: str | Path, destination_folder: str | Path) -> FileRecord:
    source = Path(source_path).resolve()
    destination = unique_destination(Path(destination_folder).resolve() / source.name)
    shutil.move(str(source), str(destination))
    return file_record_from_path(destination)


def delete_file(path: str | Path) -> None:
    Path(path).resolve().unlink()


def unique_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination

    parent = destination.parent
    stem = destination.stem
    suffix = destination.suffix
    candidate = parent / f"{stem} copy{suffix}"
    counter = 2

    while candidate.exists():
        candidate = parent / f"{stem} copy {counter}{suffix}"
        counter += 1

    return candidate
