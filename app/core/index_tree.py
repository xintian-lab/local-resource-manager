from __future__ import annotations

import os
from pathlib import Path

from app.core.indexer import FileIndexer
from app.core.scanner import normalize_path


def remap_path_prefix(path: str, old_prefix: str, new_prefix: str) -> str:
    normalized_path = normalize_path(path)
    normalized_old = normalize_path(old_prefix)
    normalized_new = normalize_path(new_prefix)
    if normalized_path == normalized_old:
        return normalized_new

    separator = "\\" if "\\" in normalized_old else "/"
    old_child_prefix = f"{normalized_old}{separator}"
    if normalized_path.startswith(old_child_prefix):
        return f"{normalized_new}{normalized_path[len(normalized_old):]}"
    return normalized_path


def sync_directory_tree(
    indexer: FileIndexer,
    directory: str,
    root_path: str,
) -> None:
    from app.core.index_sync import (
        ensure_folder_chain,
        file_record_from_path,
        folder_record_from_path,
        is_under_root,
    )

    normalized_root = normalize_path(root_path)
    normalized_directory = normalize_path(directory)
    if not is_under_root(normalized_directory, normalized_root):
        return

    ensure_folder_chain(indexer, normalized_directory, normalized_root)
    for dirpath, dirnames, filenames in os.walk(normalized_directory):
        dirnames.sort()
        filenames.sort()
        for folder_name in dirnames:
            folder_path = normalize_path(str(Path(dirpath) / folder_name))
            record = folder_record_from_path(folder_path, normalized_root)
            if record is not None:
                indexer.upsert_folder(record)
        for file_name in filenames:
            file_path = normalize_path(str(Path(dirpath) / file_name))
            record = file_record_from_path(file_path)
            if record is not None:
                ensure_folder_chain(indexer, record.folder_path, normalized_root)
                indexer.upsert_file(record)
