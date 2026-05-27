from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMenu


def add_clipboard_actions(
    menu: QMenu,
    *,
    action_paths: list[str],
    target_folder: str,
    shortcut_labels: dict[str, str],
    action_label,
) -> tuple[object | None, object | None, object | None, object, object, object | None]:
    copy_action = None
    cut_action = None
    delete_action = None
    rename_action = None
    properties_action = None

    if action_paths:
        copy_action = menu.addAction(action_label("Copy", "copy_file"))
        cut_action = menu.addAction(action_label("Cut", "cut_file"))
        delete_action = menu.addAction(action_label("Delete", "delete_file"))
        rename_action = menu.addAction("Rename")
        properties_action = menu.addAction("Properties")
        menu.addSeparator()

    new_folder_action = menu.addAction("New Folder")
    paste_action = menu.addAction(action_label("Paste", "paste_file"))
    if not target_folder:
        paste_action.setEnabled(False)
        new_folder_action.setEnabled(False)

    return (
        copy_action,
        cut_action,
        delete_action,
        new_folder_action,
        paste_action,
        rename_action,
        properties_action,
    )


def resolve_target_folder(
    item_path: str,
    item_type: str,
    default_folder: str,
) -> str:
    if item_type == "Folder" and item_path:
        return item_path
    if item_path and item_type == "File":
        return str(Path(item_path).parent)
    return default_folder


def collect_action_paths(
    item_path: str,
    item_type: str,
    selected_paths: list[str],
) -> list[str]:
    if item_path and item_path in selected_paths:
        return selected_paths
    if item_path:
        return [item_path]
    return []
