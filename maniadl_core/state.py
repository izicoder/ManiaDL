"""Per-download-folder persistence and legacy migration."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import runtime, util
from .constants import (
    LEGACY_FAILED_NAME,
    LEGACY_IDS_NAME,
    SAVE_EVERY,
    SAVE_INTERVAL,
    STATUS_NAME,
    STATUS_VERSION,
)


def scan_existing(folder: Path) -> set[int]:
    """Beatmapset IDs already present as ``NNN*.osz`` files."""
    found: set[int] = set()
    if not folder.exists():
        return found
    for path in folder.iterdir():
        match = re.match(r"(\d+)(?:[ .]|$)", path.name)
        if match and path.suffix.lower() == ".osz":
            found.add(int(match.group(1)))
    return found


class Status:
    """Atomic, batched status.json owner.

    Shape (version 2):
        {
          "version": 2,
          "updated": "...",
          "downloaded": {"123": "stamp"},
          "failed": [456],
          "titles": {"456": "Set title"}
        }

    Version 1 files are read as-is and upgraded on first save. Extra keys are
    ignored by older builds, so this stays backward compatible.
    """

    def __init__(self, folder: Path):
        self.folder = folder
        self.path = folder / STATUS_NAME
        self.downloaded: dict[str, str] = {}
        self.failed: list[int] = []
        self.titles: dict[str, str] = {}
        self.updated = ""
        self.version = STATUS_VERSION
        self._dirty = 0
        self._last_save = 0.0

    def load(self) -> "Status":
        data = None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError:
            data = None
        except ValueError:
            runtime.log(
                f"{STATUS_NAME} isn't valid JSON; rebuilding it."
            )

        if isinstance(data, dict):
            try:
                self.version = int(data.get("version") or 1)
            except (TypeError, ValueError):
                self.version = 1

            raw = data.get("downloaded") or {}
            if isinstance(raw, dict):
                self.downloaded = {str(k): str(v) for k, v in raw.items()}
            elif isinstance(raw, list):
                self.downloaded = {str(k): "" for k in raw}

            for item in data.get("failed") or []:
                try:
                    self.failed.append(int(item))
                except (TypeError, ValueError):
                    pass
            self.failed = sorted(set(self.failed))

            raw_titles = data.get("titles") or {}
            if isinstance(raw_titles, dict):
                self.titles = {
                    str(k): str(v)
                    for k, v in raw_titles.items()
                    if str(k).isdigit() and str(v).strip()
                }
            self.updated = str(data.get("updated") or "")

        self._migrate_legacy()

        # First run of this version: rewrite v1 in place as v2.
        if self.path.exists() and self.version < STATUS_VERSION:
            self.save()
        return self

    def _migrate_legacy(self) -> None:
        if self.path.exists():
            # status.json is authoritative; old text files are redundant.
            for name in (LEGACY_IDS_NAME, LEGACY_FAILED_NAME):
                (self.folder / name).unlink(missing_ok=True)
            return
        moved = []

        old_ids = self.folder / LEGACY_IDS_NAME
        try:
            stamp = util.stamp(old_ids.stat().st_mtime)
        except OSError:
            stamp = ""
        try:
            for token in old_ids.read_text(encoding="utf-8").split():
                if token.isdigit() and token not in self.downloaded:
                    self.downloaded[token] = stamp
            moved.append(LEGACY_IDS_NAME)
        except OSError:
            pass

        old_failed = self.folder / LEGACY_FAILED_NAME
        try:
            for token in old_failed.read_text(encoding="utf-8").split():
                if token.isdigit() and int(token) not in self.failed:
                    self.failed.append(int(token))
            self.failed = sorted(set(self.failed))
            moved.append(LEGACY_FAILED_NAME)
        except OSError:
            pass

        if moved:
            if self.save():
                # Keep the download folder to osz files + status.json only.
                for name in moved:
                    (self.folder / name).unlink(missing_ok=True)
                runtime.log(
                    f"Imported {' and '.join(moved)} into {STATUS_NAME} and "
                    "removed the old text files."
                )

    @property
    def ids(self) -> set[int]:
        return {int(key) for key in self.downloaded if str(key).isdigit()}

    def note_success(self, sid: int) -> None:
        self.downloaded[str(sid)] = util.stamp()
        if sid in self.failed:
            self.failed = [item for item in self.failed if item != sid]
        self.titles.pop(str(sid), None)
        self._maybe_save()

    def note_failure(self, sid: int, title: str = "") -> None:
        if sid not in self.failed:
            self.failed.append(sid)
            self.failed.sort()
        if title:
            self.titles[str(sid)] = title
        self._maybe_save()

    def prune_failed(self, present_ids: set[int]) -> None:
        """Drop failed entries that are already on disk (e.g. manual download)."""
        stale = [sid for sid in self.failed if sid in present_ids]
        if not stale:
            return
        self.failed = [sid for sid in self.failed if sid not in present_ids]
        for sid in stale:
            self.titles.pop(str(sid), None)
        self.save()

    # Backwards-compatible names used by older callers/tests.
    def mark_done(self, sid: int) -> None:
        self.note_success(sid)

    def mark_failed(self, ids, titles: dict | None = None) -> None:
        title_map = titles or {}
        for sid in ids:
            self.note_failure(int(sid), str(title_map.get(int(sid), "")))
        self.save()

    def _maybe_save(self) -> None:
        self._dirty += 1
        now = time.monotonic()
        if self._dirty >= SAVE_EVERY or now - self._last_save >= SAVE_INTERVAL:
            self.save()

    def flush(self) -> None:
        self.save()

    def save(self) -> bool:
        self.updated = util.stamp()
        ordered = sorted(
            (key for key in self.downloaded if str(key).isdigit()), key=int
        )
        failed_set = set(self.failed)
        payload = {
            "version": STATUS_VERSION,
            "updated": self.updated,
            "downloaded": {key: self.downloaded[key] for key in ordered},
            "failed": self.failed,
            "titles": {
                str(key): str(value)
                for key, value in sorted(
                    self.titles.items(),
                    key=lambda item: int(item[0]) if str(item[0]).isdigit() else 0,
                )
                if str(key).isdigit() and int(key) in failed_set
            },
        }
        try:
            util.atomic_write_text(
                self.path, json.dumps(payload, indent=2, ensure_ascii=False)
            )
            self._dirty = 0
            self._last_save = time.monotonic()
            return True
        except OSError as exc:
            runtime.log(f"Couldn't write {STATUS_NAME}: {exc}")
            return False
