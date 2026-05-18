from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class FileRecord:
    name: str
    path: str
    folder_path: str
    extension: str
    size: int
    modified_time: float


@dataclass
class FolderRecord:
    name: str
    path: str
    parent_path: str


@dataclass
class ScanResult:
    root_path: str
    files: list[FileRecord]
    folders: list[FolderRecord]
    errors: list[str]
    elapsed_seconds: float


ProgressCallback = Callable[[int, int], None]


def normalize_path(path: Path | str) -> str:
    return str(Path(path).expanduser().resolve())


class FileScanner:
    def scan(
        self,
        root_path: Path | str,
        progress_callback: ProgressCallback | None = None,
        progress_interval: int = 1000,
    ) -> ScanResult:
        started_at = time.perf_counter()
        root = Path(root_path).expanduser().resolve()
        root_string = str(root)

        files: list[FileRecord] = []
        folders: list[FolderRecord] = [
            FolderRecord(name=root.name or root_string, path=root_string, parent_path="")
        ]
        errors: list[str] = []
        stack = [root_string]
        scanned_entries = 0

        while stack:
            current_folder = stack.pop()
            try:
                with os.scandir(current_folder) as entries:
                    for entry in entries:
                        scanned_entries += 1
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                folder_path = entry.path
                                folders.append(
                                    FolderRecord(
                                        name=entry.name,
                                        path=folder_path,
                                        parent_path=current_folder,
                                    )
                                )
                                stack.append(folder_path)
                            elif entry.is_file(follow_symlinks=False):
                                stat_result = entry.stat(follow_symlinks=False)
                                files.append(
                                    FileRecord(
                                        name=entry.name,
                                        path=entry.path,
                                        folder_path=current_folder,
                                        extension=Path(entry.name).suffix.lower(),
                                        size=stat_result.st_size,
                                        modified_time=stat_result.st_mtime,
                                    )
                                )
                        except OSError as exc:
                            errors.append(f"{entry.path}: {exc}")

                        if progress_callback and scanned_entries % progress_interval == 0:
                            progress_callback(len(files), len(folders))
            except OSError as exc:
                errors.append(f"{current_folder}: {exc}")

        if progress_callback:
            progress_callback(len(files), len(folders))

        return ScanResult(
            root_path=root_string,
            files=files,
            folders=folders,
            errors=errors,
            elapsed_seconds=time.perf_counter() - started_at,
        )
