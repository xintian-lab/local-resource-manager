from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.core.paths import bookmarks_path
from app.core.scanner import normalize_path


@dataclass
class BookmarkTab:
    root_path: str
    folder_path: str
    search_query: str = ""
    label: str = ""
    open: bool = True
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @staticmethod
    def default_label(folder_path: str) -> str:
        name = Path(folder_path).name
        return name or folder_path

    def display_label(self) -> str:
        if self.label.strip():
            return self.label.strip()
        return self.default_label(self.folder_path)

    def tooltip(self) -> str:
        text = self.folder_path
        if self.search_query.strip():
            text += f"\nSearch: {self.search_query.strip()}"
        text += "\n\n× closes tab (bookmark is kept)"
        text += "\nRight-click → Delete Tab to remove permanently"
        return text

    def normalized(self) -> BookmarkTab:
        return BookmarkTab(
            id=self.id,
            label=self.label,
            root_path=normalize_path(self.root_path) if self.root_path else "",
            folder_path=normalize_path(self.folder_path) if self.folder_path else "",
            search_query=self.search_query.strip(),
            open=bool(self.open),
        )

    @classmethod
    def from_dict(cls, data: object) -> BookmarkTab | None:
        if not isinstance(data, dict):
            return None
        root_path = str(data.get("root_path", "") or "")
        folder_path = str(data.get("folder_path", "") or "")
        if not root_path or not folder_path:
            return None
        return cls(
            id=str(data.get("id", "") or uuid.uuid4()),
            label=str(data.get("label", "") or ""),
            root_path=root_path,
            folder_path=folder_path,
            search_query=str(data.get("search_query", "") or ""),
            open=bool(data.get("open", True)),
        ).normalized()


def load_bookmarks() -> tuple[list[BookmarkTab], str]:
    path = bookmarks_path()
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return [], ""

    if not isinstance(data, dict):
        return [], ""

    active_tab_id = str(data.get("active_tab_id", "") or "")
    raw_tabs = data.get("tabs", [])
    if not isinstance(raw_tabs, list):
        return [], active_tab_id

    tabs: list[BookmarkTab] = []
    for raw_tab in raw_tabs:
        tab = BookmarkTab.from_dict(raw_tab)
        if tab is not None:
            tabs.append(tab)
    return tabs, active_tab_id


def save_bookmarks(tabs: list[BookmarkTab], active_tab_id: str) -> None:
    path = bookmarks_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "active_tab_id": active_tab_id,
        "tabs": [asdict(tab.normalized()) for tab in tabs],
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
