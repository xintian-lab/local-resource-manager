from __future__ import annotations

from PySide6.QtGui import QKeySequence

SEARCH_MODE_DEBOUNCED = "debounced"
SEARCH_MODE_ENTER = "enter"
DEFAULT_SEARCH_MODE = SEARCH_MODE_ENTER
DEFAULT_DEBOUNCE_MS = 300
DEFAULT_RESULTS_PAGE_SIZE = 300
KEYBOARD_FOLDER_REFRESH_IMMEDIATE = "immediate"
KEYBOARD_FOLDER_REFRESH_ON_ENTER = "on_enter"
DEFAULT_KEYBOARD_FOLDER_REFRESH = KEYBOARD_FOLDER_REFRESH_IMMEDIATE
DEFAULT_THEME = "classic_dark"
THEME_CUSTOM = "custom"
DEFAULT_SHOW_FILE_ICONS = True
DEFAULT_SHOW_FOLDER_ICONS = True
DEFAULT_KEYBOARD_MODE_ENABLED = True

DEFAULT_CUSTOM_THEME_COLORS = {
    "background": "#1e1e1e",
    "surface": "#252526",
    "alternate_surface": "#2d3033",
    "text": "#cccccc",
    "border": "#3c3c3c",
}

THEME_COLOR_KEYS = (
    "background",
    "surface",
    "alternate_surface",
    "text",
    "border",
)

THEME_COLOR_LABELS = {
    "background": "Background",
    "surface": "Surface",
    "alternate_surface": "Alternate surface",
    "text": "Text",
    "border": "Border",
}

THEMES = {
    "classic_dark": {
        "label": "Classic Dark (Default)",
        "background": "#1e1e1e",
        "surface": "#252526",
        "alternate_surface": "#2d3033",
        "text": "#cccccc",
        "border": "#3c3c3c",
    },
    "light": {
        "label": "Light White",
        "background": "#ffffff",
        "surface": "#ffffff",
        "alternate_surface": "#f3f4f6",
        "text": "#111111",
        "border": "#d0d7de",
    },
    "warm": {
        "label": "Warm Cream",
        "background": "#fff7ed",
        "surface": "#fffaf3",
        "alternate_surface": "#fff4e6",
        "text": "#1f1f1f",
        "border": "#ead6bd",
    },
    "mung_bean": {
        "label": "Mung Bean Green",
        "background": "#c7edcc",
        "surface": "#ddf4df",
        "alternate_surface": "#d4f0d9",
        "text": "#1f2d1f",
        "border": "#9fc9a4",
    },
    "sakura": {
        "label": "Sakura Pink",
        "background": "#f8d7df",
        "surface": "#fde8ed",
        "alternate_surface": "#fce4eb",
        "text": "#2d1f25",
        "border": "#e5a8b8",
    },
    "cool": {
        "label": "Cool Blue",
        "background": "#eff6ff",
        "surface": "#f8fbff",
        "alternate_surface": "#eef4fc",
        "text": "#111827",
        "border": "#bfdbfe",
    },
    "gray": {
        "label": "Light Gray",
        "background": "#f3f4f6",
        "surface": "#ffffff",
        "alternate_surface": "#eceef2",
        "text": "#111827",
        "border": "#d1d5db",
    },
    "dark": {
        "label": "Dark Slate",
        "background": "#1f2937",
        "surface": "#111827",
        "alternate_surface": "#1b2533",
        "text": "#f9fafb",
        "border": "#4b5563",
    },
    THEME_CUSTOM: {
        "label": "Custom",
        **DEFAULT_CUSTOM_THEME_COLORS,
    },
}

DEFAULT_KEY_BINDINGS = {
    "focus_search": "Ctrl+F",
    "clear_search": "Esc",
    "select_root": "Ctrl+O",
    "new_tab": "Ctrl+T",
    "pin_folder": "Ctrl+P",
    "copy_file": "Ctrl+C",
    "cut_file": "Ctrl+X",
    "paste_file": "Ctrl+V",
    "delete_file": "Del",
    "scroll_folders_left": "A",
    "scroll_folders_right": "D",
    "scroll_files_up": "W",
    "scroll_files_down": "S",
}

KEY_BINDING_LABELS = {
    "focus_search": "Focus search box",
    "clear_search": "Clear search",
    "select_root": "Select root folder",
    "new_tab": "New tab from current location",
    "pin_folder": "Pin/unpin folder",
    "copy_file": "Copy selected file",
    "cut_file": "Cut selected file",
    "paste_file": "Paste into current folder",
    "delete_file": "Delete selected file",
    "scroll_folders_left": "Folder columns left",
    "scroll_folders_right": "Folder columns right",
    "scroll_files_up": "Hovered area up",
    "scroll_files_down": "Hovered area down",
}


def normalize_key_sequence(value: object) -> str:
    sequence = QKeySequence(str(value or ""))
    normalized = sequence.toString(QKeySequence.SequenceFormat.PortableText)
    if normalized == "Backspace":
        return ""
    return normalized


def normalize_custom_theme_colors(value: object) -> dict[str, str]:
    colors = dict(DEFAULT_CUSTOM_THEME_COLORS)
    if not isinstance(value, dict):
        return colors
    for key in THEME_COLOR_KEYS:
        raw = value.get(key)
        if isinstance(raw, str) and raw.strip():
            colors[key] = raw.strip()
    return colors


def resolve_theme(theme_name: str, custom_colors: dict[str, str] | None = None) -> dict[str, str]:
    if theme_name not in THEMES:
        theme_name = DEFAULT_THEME
    if theme_name == THEME_CUSTOM:
        merged = normalize_custom_theme_colors(custom_colors or {})
        return {**THEMES[THEME_CUSTOM], **merged}
    return THEMES[theme_name]
