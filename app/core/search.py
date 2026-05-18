from __future__ import annotations

import sqlite3

from app.core.indexer import FileIndexer


class SearchService:
    def __init__(self, indexer: FileIndexer) -> None:
        self.indexer = indexer
        self._visible_folder_cache: dict[str, set[str]] = {}
        self._folder_match_count_cache: dict[str, dict[str, int]] = {}

    def child_folders(
        self,
        parent_path: str,
        query: str = "",
        include_counts: bool = False,
    ) -> list[object]:
        normalized = self.normalize(query)
        children = self.indexer.get_child_folders(parent_path)
        if not normalized:
            return children

        visible_paths = self._visible_folder_paths(normalized)
        filtered_children = [child for child in children if str(child["path"]) in visible_paths]
        if not include_counts:
            return filtered_children

        match_counts = self.folder_match_counts(normalized)
        return [
            {
                "path": child["path"],
                "name": child["name"],
                "parent_path": child["parent_path"],
                "match_count": match_counts.get(str(child["path"]), 0),
            }
            for child in filtered_children
        ]

    def files_in_folder(self, folder_path: str, query: str = "") -> list[sqlite3.Row]:
        return self.indexer.get_files_in_folder(folder_path, self.normalize(query))

    def results_in_folder_tree(
        self,
        folder_path: str,
        query: str,
        limit: int = 1000,
        offset: int = 0,
    ) -> tuple[list[dict[str, object]], int]:
        return self.indexer.search_results_in_folder_tree(
            folder_path,
            self.normalize(query),
            limit,
            offset,
        )

    def normalize(self, query: str) -> str:
        return query.strip().lower()

    def clear_cache(self) -> None:
        self._visible_folder_cache.clear()
        self._folder_match_count_cache.clear()

    def folder_match_counts(self, query: str) -> dict[str, int]:
        normalized = self.normalize(query)
        if not normalized:
            return {}
        if normalized in self._folder_match_count_cache:
            return self._folder_match_count_cache[normalized]

        folders = self.indexer.get_all_folders()
        parent_by_path = {
            str(folder["path"]): str(folder["parent_path"])
            for folder in folders
        }
        counts: dict[str, int] = {}
        direct_counts = self.indexer.get_matching_file_folder_counts(normalized)

        for path, count in direct_counts.items():
            self._add_count_to_path_and_ancestors(path, count, parent_by_path, counts)

        self._folder_match_count_cache[normalized] = counts
        return counts

    def _visible_folder_paths(self, query: str) -> set[str]:
        if query in self._visible_folder_cache:
            return self._visible_folder_cache[query]

        folders = self.indexer.get_all_folders()
        parent_by_path = {
            str(folder["path"]): str(folder["parent_path"])
            for folder in folders
        }
        visible_paths: set[str] = set()
        matched_paths = set(self.indexer.get_matching_folder_paths(query))
        matched_paths.update(self.indexer.get_matching_file_folder_paths(query))

        for path in matched_paths:
            self._add_path_and_ancestors(path, parent_by_path, visible_paths)

        self._visible_folder_cache[query] = visible_paths
        return visible_paths

    def _add_path_and_ancestors(
        self,
        path: str,
        parent_by_path: dict[str, str],
        visible_paths: set[str],
    ) -> None:
        current = path
        while current:
            visible_paths.add(current)
            current = parent_by_path.get(current, "")

    def _add_count_to_path_and_ancestors(
        self,
        path: str,
        count: int,
        parent_by_path: dict[str, str],
        counts: dict[str, int],
    ) -> None:
        current = path
        while current:
            counts[current] = counts.get(current, 0) + count
            current = parent_by_path.get(current, "")
