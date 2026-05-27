from __future__ import annotations

MIN_SEARCH_QUERY_LENGTH = 2
LARGE_INDEX_FILE_COUNT = 100_000
DEFAULT_SHOW_FOLDER_MATCH_COUNTS = True
DEFAULT_WATCH_INDEX_CHANGES = False
DEFAULT_SEARCH_SUBTREE_RESULTS = True


def is_searchable_query(query: str) -> bool:
    normalized = query.strip().lower()
    if not normalized:
        return False
    return len(normalized) >= MIN_SEARCH_QUERY_LENGTH
