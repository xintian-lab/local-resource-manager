from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from app.core.index_sync import IndexEvent, apply_index_events
from app.core.indexer import FileIndexer
from app.core.scanner import normalize_path


class _IndexWatchHandler(FileSystemEventHandler):
    def __init__(self, enqueue) -> None:
        super().__init__()
        self._enqueue = enqueue

    def on_created(self, event) -> None:
        if isinstance(event, DirCreatedEvent):
            self._enqueue(IndexEvent("dir_created", event.src_path))
        elif isinstance(event, FileCreatedEvent):
            self._enqueue(IndexEvent("file_created", event.src_path))

    def on_deleted(self, event) -> None:
        if isinstance(event, DirDeletedEvent):
            self._enqueue(IndexEvent("dir_deleted", event.src_path))
        elif isinstance(event, FileDeletedEvent):
            self._enqueue(IndexEvent("file_deleted", event.src_path))

    def on_modified(self, event) -> None:
        if isinstance(event, FileModifiedEvent) and not event.is_directory:
            self._enqueue(IndexEvent("file_modified", event.src_path))

    def on_moved(self, event) -> None:
        if isinstance(event, DirMovedEvent):
            self._enqueue(
                IndexEvent("dir_moved", event.src_path, event.dest_path),
            )
        elif isinstance(event, FileMovedEvent):
            self._enqueue(
                IndexEvent("file_moved", event.src_path, event.dest_path),
            )


class IndexWatcher(QObject):
    changes_ready = Signal(object)
    _event_received = Signal(object)

    def __init__(self, parent: QObject | None = None, debounce_ms: int = 400) -> None:
        super().__init__(parent)
        self._debounce_ms = debounce_ms
        self._root_path = ""
        self._indexer: FileIndexer | None = None
        self._observer: Observer | None = None
        self._pending_events: list[IndexEvent] = []
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._flush)
        self._event_received.connect(self._enqueue_on_main_thread)

    def is_running(self) -> bool:
        return self._observer is not None

    def start(self, root_path: str, indexer: FileIndexer) -> None:
        self.stop()
        normalized_root = normalize_path(root_path)
        self._root_path = normalized_root
        self._indexer = indexer

        handler = _IndexWatchHandler(self._emit_event)
        observer = Observer()
        observer.schedule(handler, normalized_root, recursive=True)
        observer.start()
        self._observer = observer

    def stop(self) -> None:
        self._debounce_timer.stop()
        self._pending_events.clear()
        observer = self._observer
        self._observer = None
        if observer is not None:
            observer.stop()
            observer.join(timeout=5)
        self._root_path = ""
        self._indexer = None

    def _emit_event(self, event: IndexEvent) -> None:
        self._event_received.emit(event)

    def _enqueue_on_main_thread(self, event: IndexEvent) -> None:
        self._pending_events.append(event)
        self._debounce_timer.start(self._debounce_ms)

    def _flush(self) -> None:
        events = self._pending_events
        self._pending_events = []
        if not events or self._indexer is None or not self._root_path:
            return

        affected_folders = apply_index_events(self._indexer, self._root_path, events)
        if affected_folders:
            self.changes_ready.emit(affected_folders)
