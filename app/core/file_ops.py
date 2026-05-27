from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
from pathlib import Path

from app.core.scanner import FileRecord, normalize_path


def open_file(path: str | Path) -> None:
    target = Path(path)
    system = platform.system()

    if system == "Windows":
        os.startfile(target)  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


def _windows_open_with_dialog(target: Path) -> None:
    """Show the system 'Open with' dialog (same mechanism as Explorer)."""
    resolved = str(target.resolve())
    rundll32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "rundll32.exe"
    subprocess.Popen(
        [str(rundll32), "shell32.dll,OpenAs_RunDLL", resolved],
        close_fds=True,
    )


def _windows_open_with_app(target: Path, application: Path) -> None:
    result = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
        None,
        "open",
        str(application.resolve()),
        str(target.resolve()),
        str(target.parent),
        1,
    )
    if result <= 32:
        raise OSError(f"ShellExecute failed with code {result}")


def open_file_with(path: str | Path, application: str | Path | None = None) -> None:
    target = Path(path)
    system = platform.system()

    if system == "Windows":
        if application is None:
            _windows_open_with_dialog(target)
        else:
            _windows_open_with_app(target, Path(application))
        return

    if system == "Darwin":
        if application is None:
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["open", "-a", str(application), str(target)])
        return

    if application is None:
        subprocess.Popen(["xdg-open", str(target)])
    else:
        subprocess.Popen([str(application), str(target)])


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


def validate_entry_name(name: str) -> None:
    cleaned = name.strip()
    if not cleaned or cleaned in {".", ".."}:
        raise OSError("Name cannot be empty.")
    if any(character in cleaned for character in '\\/:*?"<>|'):
        raise OSError('Name cannot contain any of \\ / : * ? " < > |')


def rename_entry(path: str | Path, new_name: str) -> Path:
    validate_entry_name(new_name)
    source = Path(path).resolve()
    destination = source.with_name(new_name.strip())
    if destination.exists():
        raise OSError(f'"{destination.name}" already exists.')
    source.rename(destination)
    return destination


def unique_folder_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination

    parent = destination.parent
    base_name = destination.name or "New folder"
    candidate = parent / f"{base_name} copy"
    counter = 2
    while candidate.exists():
        candidate = parent / f"{base_name} copy {counter}"
        counter += 1
    return candidate


def create_folder(parent_folder: str | Path, name: str = "New folder") -> Path:
    parent = Path(parent_folder).resolve()
    if not parent.is_dir():
        raise OSError("Parent folder does not exist.")
    validate_entry_name(name)
    destination = unique_folder_destination(parent / name.strip())
    destination.mkdir(parents=False, exist_ok=False)
    return destination


def copy_entry_to_folder(source_path: str | Path, destination_folder: str | Path) -> Path:
    source = Path(source_path).resolve()
    destination_parent = Path(destination_folder).resolve()
    if not destination_parent.is_dir():
        raise OSError("Destination folder does not exist.")
    if source.is_dir():
        destination = unique_folder_destination(destination_parent / source.name)
        shutil.copytree(source, destination)
        return destination
    return Path(copy_file_to_folder(source, destination_parent).path)


def move_entry_to_folder(source_path: str | Path, destination_folder: str | Path) -> Path:
    source = Path(source_path).resolve()
    destination_parent = Path(destination_folder).resolve()
    if not destination_parent.is_dir():
        raise OSError("Destination folder does not exist.")
    if source.is_dir():
        destination = unique_folder_destination(destination_parent / source.name)
        shutil.move(str(source), str(destination))
        return destination
    return Path(move_file_to_folder(source, destination_parent).path)


def is_path_descendant(path: str | Path, ancestor: str | Path) -> bool:
    normalized_path = normalize_path(str(Path(path).resolve()))
    normalized_ancestor = normalize_path(str(Path(ancestor).resolve()))
    if normalized_path == normalized_ancestor:
        return False
    separator = "\\" if "\\" in normalized_ancestor else "/"
    return normalized_path.startswith(f"{normalized_ancestor}{separator}")


def _windows_send_to_recycle_bin(target: Path) -> None:
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.WORD),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 0x0003
    FOF_ALLOWUNDO = 0x0040
    FOF_NOCONFIRMATION = 0x0010
    FOF_SILENT = 0x0004

    from_buffer = str(target) + "\0\0"
    operation = SHFILEOPSTRUCTW()
    operation.hwnd = None
    operation.wFunc = FO_DELETE
    operation.pFrom = from_buffer
    operation.pTo = None
    operation.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted:
        raise OSError(f"Could not move item to Recycle Bin (code {result}).")


def send_to_recycle_bin(path: str | Path) -> None:
    target = Path(path).resolve()
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {target}")

    system = platform.system()
    if system == "Windows":
        _windows_send_to_recycle_bin(target)
        return
    if system == "Darwin":
        subprocess.run(
            ["osascript", "-e", f'tell application "Finder" to delete POSIX file "{target}"'],
            check=True,
        )
        return

    try:
        subprocess.run(["gio", "trash", str(target)], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise OSError("Recycle Bin is unavailable on this system.") from exc


def get_path_stat(path: str | Path) -> os.stat_result:
    return Path(path).resolve().stat()



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
