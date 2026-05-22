from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.core.indexer import FileIndexer
from app.core.scanner import FileRecord, FolderRecord, normalize_path


@dataclass(frozen=True)
class IndexEvent:
    event_type: str
    src_path: str
    dest_path: str = ""


def is_under_root(path: str, root_path: str) -> bool:
    normalized_path = normalize_path(path)
    normalized_root = normalize_path(root_path)
    if normalized_path == normalized_root:
        return True
    return normalized_path.startswith(f"{normalized_root}{os.sep}")


def file_record_from_path(path: str) -> FileRecord | None:
    file_path = Path(path)
    try:
        if not file_path.is_file():
            return None
        stat_result = file_path.stat()
    except OSError:
        return None

    resolved = str(file_path.resolve())
    return FileRecord(
        name=file_path.name,
        path=resolved,
        folder_path=str(file_path.parent.resolve()),
        extension=file_path.suffix.lower(),
        size=stat_result.st_size,
        modified_time=stat_result.st_mtime,
    )


def folder_record_from_path(path: str, root_path: str) -> FolderRecord | None:
    folder_path = normalize_path(path)
    normalized_root = normalize_path(root_path)
    directory = Path(folder_path)
    try:
        if not directory.is_dir():
            return None
    except OSError:
        return None

    if not is_under_root(folder_path, normalized_root):
        return None

    if folder_path == normalized_root:
        parent_path = ""
    else:
        parent_path = normalize_path(str(directory.parent))

    return FolderRecord(
        name=directory.name or folder_path,
        path=folder_path,
        parent_path=parent_path,
    )


def ensure_folder_chain(
    indexer: FileIndexer,
    folder_path: str,
    root_path: str,
) -> None:
    normalized_root = normalize_path(root_path)
    current = normalize_path(folder_path)
    if not is_under_root(current, normalized_root):
        return

    chain: list[str] = []
    while True:
        chain.append(current)
        if current == normalized_root:
            break
        parent = normalize_path(str(Path(current).parent))
        if parent == current:
            break
        current = parent

    for path in reversed(chain):
        record = folder_record_from_path(path, normalized_root)
        if record is not None:
            indexer.upsert_folder(record)


def apply_index_events(
    indexer: FileIndexer,
    root_path: str,
    events: list[IndexEvent],
) -> set[str]:
    normalized_root = normalize_path(root_path)
    affected_folders: set[str] = set()

    def mark(path: str) -> None:
        normalized_path = normalize_path(path)
        if is_under_root(normalized_path, normalized_root):
            affected_folders.add(normalized_path)
            affected_folders.add(normalize_path(str(Path(normalized_path).parent)))

    for event in events:
        if event.event_type == "file_moved":
            if event.src_path:
                mark(event.src_path)
                indexer.delete_file(normalize_path(event.src_path))
            if event.dest_path:
                mark(event.dest_path)
                record = file_record_from_path(event.dest_path)
                if record is not None:
                    ensure_folder_chain(indexer, record.folder_path, normalized_root)
                    indexer.upsert_file(record)
            continue

        if event.event_type == "dir_moved":
            if event.src_path and is_under_root(event.src_path, normalized_root):
                mark(event.src_path)
                indexer.delete_folder_subtree(normalize_path(event.src_path))
            if event.dest_path and is_under_root(event.dest_path, normalized_root):
                mark(event.dest_path)
                record = folder_record_from_path(event.dest_path, normalized_root)
                if record is not None:
                    ensure_folder_chain(indexer, record.parent_path or normalized_root, normalized_root)
                    indexer.upsert_folder(record)
            continue

        path = event.src_path
        if not path or not is_under_root(path, normalized_root):
            continue

        normalized_path = normalize_path(path)
        mark(normalized_path)

        if event.event_type == "file_deleted":
            indexer.delete_file(normalized_path)
        elif event.event_type == "dir_deleted":
            indexer.delete_folder_subtree(normalized_path)
        elif event.event_type == "file_modified":
            record = file_record_from_path(normalized_path)
            if record is not None:
                ensure_folder_chain(indexer, record.folder_path, normalized_root)
                indexer.upsert_file(record)
            else:
                indexer.delete_file(normalized_path)
        elif event.event_type == "file_created":
            record = file_record_from_path(normalized_path)
            if record is not None:
                ensure_folder_chain(indexer, record.folder_path, normalized_root)
                indexer.upsert_file(record)
        elif event.event_type == "dir_created":
            record = folder_record_from_path(normalized_path, normalized_root)
            if record is not None:
                ensure_folder_chain(indexer, record.parent_path or normalized_root, normalized_root)
                indexer.upsert_folder(record)

    return {folder for folder in affected_folders if folder}
