"""Thread-safe progress snapshots shared by the download job and the GUI.

The downloader only needs ``add_task`` / ``update`` / ``remove_task`` (the
subset of the rich Progress API it used before), so this small board replaces
rich in the GUI build. The GUI polls :meth:`TaskBoard.snapshot` from the Tk
thread while downloads run in a worker thread.
"""

from __future__ import annotations

import threading


class TaskBoard:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[int, dict] = {}
        self._next = 1
        self._message = ""

    def reset(self) -> None:
        with self._lock:
            self._tasks.clear()
            self._next = 1
            self._message = ""

    def add_task(self, description: str, total: float | None = None) -> int:
        with self._lock:
            task_id = self._next
            self._next += 1
            self._tasks[task_id] = {
                "description": str(description),
                "completed": 0.0,
                "total": float(total) if total else None,
            }
            return task_id

    def update(self, task_id: int, **kwargs) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            if kwargs.get("description") is not None:
                task["description"] = str(kwargs["description"])
            if kwargs.get("total") is not None:
                task["total"] = float(kwargs["total"])
            if kwargs.get("completed") is not None:
                task["completed"] = float(kwargs["completed"])
            if kwargs.get("advance") is not None:
                task["completed"] += float(kwargs["advance"])

    def remove_task(self, task_id: int) -> None:
        with self._lock:
            self._tasks.pop(task_id, None)

    def set_message(self, message: str) -> None:
        with self._lock:
            self._message = str(message)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "message": self._message,
                "tasks": [
                    {"id": task_id, **task}
                    for task_id, task in sorted(self._tasks.items())
                ],
            }


class StatusSink:
    """Adapter for ``api.search_sets``, which only needs ``update(text)``."""

    def __init__(self, board: TaskBoard) -> None:
        self.board = board
        self.last = ""

    def update(self, message: str) -> None:
        self.last = str(message)
        setter = getattr(self.board, "set_message", None)
        if setter is not None:
            setter(self.last)
