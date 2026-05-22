from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, Iterable

from app.core.paths import database_path
from app.core.scanner import FileRecord, FolderRecord, ScanCancelledError
from app.core.search_constants import is_searchable_query


DEFAULT_DB_PATH = database_path()


class FileIndexer:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE,
                    folder_path TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    modified_time REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS folders (
                    path TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    parent_path TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_files_folder_path
                    ON files(folder_path);
                CREATE INDEX IF NOT EXISTS idx_files_extension
                    ON files(extension);
                CREATE INDEX IF NOT EXISTS idx_files_name
                    ON files(name);
                CREATE INDEX IF NOT EXISTS idx_folders_parent_path
                    ON folders(parent_path);
                CREATE INDEX IF NOT EXISTS idx_folders_name
                    ON folders(name);
                """
            )

    def replace_index(
        self,
        files: Iterable[FileRecord],
        folders: Iterable[FolderRecord],
        cancel_check: Callable[[], bool] | None = None,
        batch_size: int = 5000,
    ) -> None:
        folder_rows = [(folder.path, folder.name, folder.parent_path) for folder in folders]
        file_rows = [
            (
                file.name,
                file.path,
                file.folder_path,
                file.extension,
                file.size,
                file.modified_time,
            )
            for file in files
        ]

        with self._connect() as connection:
            connection.execute("BEGIN")
            try:
                connection.execute("DELETE FROM files")
                connection.execute("DELETE FROM folders")

                for start in range(0, len(folder_rows), batch_size):
                    if cancel_check and cancel_check():
                        raise ScanCancelledError()
                    connection.executemany(
                        """
                        INSERT INTO folders (path, name, parent_path)
                        VALUES (?, ?, ?)
                        ON CONFLICT(path) DO UPDATE SET
                            name = excluded.name,
                            parent_path = excluded.parent_path
                        """,
                        folder_rows[start : start + batch_size],
                    )

                for start in range(0, len(file_rows), batch_size):
                    if cancel_check and cancel_check():
                        raise ScanCancelledError()
                    connection.executemany(
                        """
                        INSERT INTO files (
                            name,
                            path,
                            folder_path,
                            extension,
                            size,
                            modified_time
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        file_rows[start : start + batch_size],
                    )

                if cancel_check and cancel_check():
                    raise ScanCancelledError()
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def get_child_folders(self, parent_path: str, query: str = "") -> list[sqlite3.Row]:
        if not query.strip():
            with self._connect() as connection:
                return list(
                    connection.execute(
                        """
                        SELECT path, name, parent_path
                        FROM folders
                        WHERE parent_path = ?
                        ORDER BY lower(name)
                        """,
                        (parent_path,),
                    )
                )

        normalized = query.strip().lower()
        like_term = f"%{normalized}%"
        extension = normalized if normalized.startswith(".") else f".{normalized}"
        child_prefix = f"{self._path_separator(parent_path)}%"
        sql = """
            SELECT child.path, child.name, child.parent_path
            FROM folders child
            WHERE child.parent_path = ?
              AND (
                  child.name LIKE ? COLLATE NOCASE
                  OR EXISTS (
                      SELECT 1
                      FROM folders descendant
                      WHERE (
                          descendant.path = child.path
                          OR descendant.path LIKE child.path || ?
                      )
                        AND descendant.name LIKE ? COLLATE NOCASE
                      LIMIT 1
                  )
                  OR EXISTS (
                      SELECT 1
                      FROM files matched_file
                      WHERE (
                          matched_file.folder_path = child.path
                          OR matched_file.folder_path LIKE child.path || ?
                      )
                        AND (
                            matched_file.name LIKE ? COLLATE NOCASE
                            OR matched_file.extension = ?
                        )
                      LIMIT 1
                  )
              )
            ORDER BY lower(child.name)
        """
        with self._connect() as connection:
            return list(
                connection.execute(
                    sql,
                    (
                        parent_path,
                        like_term,
                        child_prefix,
                        like_term,
                        child_prefix,
                        like_term,
                        extension,
                    ),
                )
            )

    def get_all_folders(self) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT path, name, parent_path
                    FROM folders
                    """
                )
            )

    def get_matching_folder_paths(self, query: str) -> list[str]:
        normalized = query.strip().lower()
        if not normalized or not is_searchable_query(normalized):
            return []

        like_term = f"%{normalized}%"
        with self._connect() as connection:
            return [
                str(row["path"])
                for row in connection.execute(
                    """
                    SELECT path
                    FROM folders
                    WHERE name LIKE ? COLLATE NOCASE
                    """,
                    (like_term,),
                )
            ]

    def get_matching_file_folder_paths(self, query: str) -> list[str]:
        normalized = query.strip().lower()
        if not normalized or not is_searchable_query(normalized):
            return []

        where_clause, params = self._file_match_clause(query)
        sql = f"""
            SELECT DISTINCT folder_path
            FROM files
            WHERE 1 = 1
            {where_clause}
        """
        with self._connect() as connection:
            return [
                str(row["folder_path"])
                for row in connection.execute(sql, params)
            ]

    def get_matching_file_folder_counts(self, query: str) -> dict[str, int]:
        normalized = query.strip().lower()
        if not normalized or not is_searchable_query(normalized):
            return {}

        where_clause, params = self._file_match_clause(query)
        if not where_clause:
            return {}

        sql = f"""
            SELECT folder_path, COUNT(*) AS count
            FROM files
            WHERE 1 = 1
            {where_clause}
            GROUP BY folder_path
        """
        with self._connect() as connection:
            return {
                str(row["folder_path"]): int(row["count"])
                for row in connection.execute(sql, params)
            }

    def get_files_in_folder(
        self,
        folder_path: str,
        query: str = "",
        limit: int = 1000,
        offset: int = 0,
    ) -> tuple[list[sqlite3.Row], int]:
        normalized = query.strip().lower()
        if normalized and not is_searchable_query(normalized):
            return [], 0

        where_clause, params = self._file_match_clause(query)
        count_sql = f"""
            SELECT COUNT(*) AS count
            FROM files
            WHERE folder_path = ?
            {where_clause}
        """
        page_sql = f"""
            SELECT id, name, path, folder_path, extension, size, modified_time
            FROM files
            WHERE folder_path = ?
            {where_clause}
            ORDER BY lower(name)
            LIMIT ? OFFSET ?
        """
        with self._connect() as connection:
            total_row = connection.execute(count_sql, (folder_path, *params)).fetchone()
            rows = connection.execute(
                page_sql,
                (folder_path, *params, limit, offset),
            )
            return list(rows), int(total_row["count"])

    def search_results_in_folder_tree(
        self,
        folder_path: str,
        query: str,
        limit: int = 1000,
        offset: int = 0,
    ) -> tuple[list[dict[str, object]], int]:
        normalized = query.strip().lower()
        if not normalized or not is_searchable_query(normalized):
            return [], 0

        folder_like_term = f"%{normalized}%"
        file_where_clause, file_params = self._file_match_clause(normalized)
        child_prefix = f"{folder_path}{self._path_separator(folder_path)}%"
        union_sql = f"""
            SELECT
                'Folder' AS result_type,
                0 AS result_sort,
                '' AS id,
                name,
                path,
                parent_path AS folder_path,
                '' AS extension,
                '' AS size,
                '' AS modified_time
            FROM folders
            WHERE (path = ? OR path LIKE ?)
              AND name LIKE ? COLLATE NOCASE

            UNION ALL

            SELECT
                'File' AS result_type,
                1 AS result_sort,
                id,
                name,
                path,
                folder_path,
                extension,
                size,
                modified_time
            FROM files
            WHERE (folder_path = ? OR folder_path LIKE ?)
            {file_where_clause}
        """
        params = (
            folder_path,
            child_prefix,
            folder_like_term,
            folder_path,
            child_prefix,
            *file_params,
        )
        count_sql = f"SELECT COUNT(*) AS count FROM ({union_sql})"
        page_sql = f"""
            SELECT result_type, id, name, path, folder_path, extension, size, modified_time
            FROM ({union_sql})
            ORDER BY result_sort, lower(name), lower(path)
            LIMIT ? OFFSET ?
        """

        with self._connect() as connection:
            total_row = connection.execute(count_sql, params).fetchone()
            rows = connection.execute(page_sql, (*params, limit, offset))
            results = [
                {
                    "result_type": "File",
                    "id": row["id"],
                    "name": row["name"],
                    "path": row["path"],
                    "folder_path": row["folder_path"],
                    "extension": row["extension"],
                    "size": row["size"],
                    "modified_time": row["modified_time"],
                }
                if row["result_type"] == "File"
                else {
                    "result_type": "Folder",
                    "id": row["id"],
                    "name": row["name"],
                    "path": row["path"],
                    "folder_path": row["folder_path"],
                    "extension": row["extension"],
                    "size": row["size"],
                    "modified_time": row["modified_time"],
                }
                for row in rows
            ]
            return results, int(total_row["count"])

    def upsert_folder(self, folder: FolderRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO folders (path, name, parent_path)
                VALUES (?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    name = excluded.name,
                    parent_path = excluded.parent_path
                """,
                (folder.path, folder.name, folder.parent_path),
            )

    def delete_folder_subtree(self, folder_path: str) -> None:
        child_prefix = f"{folder_path}{self._path_separator(folder_path)}%"
        with self._connect() as connection:
            connection.execute("BEGIN")
            connection.execute(
                """
                DELETE FROM files
                WHERE folder_path = ? OR folder_path LIKE ?
                """,
                (folder_path, child_prefix),
            )
            connection.execute(
                """
                DELETE FROM folders
                WHERE path = ? OR path LIKE ?
                """,
                (folder_path, child_prefix),
            )
            connection.commit()

    def upsert_file(self, file: FileRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO files (
                    name,
                    path,
                    folder_path,
                    extension,
                    size,
                    modified_time
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    name = excluded.name,
                    folder_path = excluded.folder_path,
                    extension = excluded.extension,
                    size = excluded.size,
                    modified_time = excluded.modified_time
                """,
                (
                    file.name,
                    file.path,
                    file.folder_path,
                    file.extension,
                    file.size,
                    file.modified_time,
                ),
            )

    def delete_file(self, path: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM files WHERE path = ?", (path,))

    def move_file_record(self, old_path: str, file: FileRecord) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN")
            connection.execute("DELETE FROM files WHERE path = ?", (old_path,))
            connection.execute(
                """
                INSERT INTO files (
                    name,
                    path,
                    folder_path,
                    extension,
                    size,
                    modified_time
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    file.name,
                    file.path,
                    file.folder_path,
                    file.extension,
                    file.size,
                    file.modified_time,
                ),
            )
            connection.commit()

    def folder_contains_matches(self, folder_path: str, query: str) -> bool:
        normalized = query.strip().lower()
        if not normalized or not is_searchable_query(normalized):
            return False

        where_clause, params = self._file_match_clause(query)
        like_term = f"%{normalized}%"
        child_prefix = f"{folder_path}{self._path_separator(folder_path)}%"
        sql = f"""
            SELECT 1
            WHERE EXISTS (
                SELECT 1
                FROM folders
                WHERE (path = ? OR path LIKE ?)
                  AND name LIKE ? COLLATE NOCASE
                LIMIT 1
            )
            OR EXISTS (
                SELECT 1
                FROM files
                WHERE (folder_path = ? OR folder_path LIKE ?)
                {where_clause}
                LIMIT 1
            )
        """
        with self._connect() as connection:
            row = connection.execute(
                sql,
                (
                    folder_path,
                    child_prefix,
                    like_term,
                    folder_path,
                    child_prefix,
                    *params,
                ),
            ).fetchone()
            return row is not None

    def get_file_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM files").fetchone()
            return int(row["count"])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA temp_store=MEMORY")
        return connection

    def _file_match_clause(self, query: str) -> tuple[str, tuple[str, ...]]:
        normalized = query.strip().lower()
        if not normalized:
            return "", ()

        like_term = f"%{normalized}%"
        extension = normalized if normalized.startswith(".") else f".{normalized}"
        if normalized.startswith("."):
            return "AND extension = ?", (extension,)

        return (
            "AND (name LIKE ? COLLATE NOCASE OR extension = ?)",
            (like_term, extension),
        )

    def _path_separator(self, path: str) -> str:
        return "\\" if "\\" in path else "/"
