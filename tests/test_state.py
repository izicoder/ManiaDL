import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from maniadl_core import state


class StatusMigrationTests(unittest.TestCase):
    def test_v1_is_upgraded_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "status.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "downloaded": {"11": "old"},
                        "failed": [22],
                    }
                ),
                encoding="utf-8",
            )
            status = state.Status(folder).load()
            payload = json.loads((folder / "status.json").read_text("utf-8"))
            self.assertEqual(payload["version"], 2)
            self.assertEqual(status.ids, {11})
            self.assertEqual(status.failed, [22])
            self.assertEqual(payload["titles"], {})

    def test_legacy_text_files_are_imported(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "downloaded_ids.txt").write_text("33 44", encoding="utf-8")
            (folder / "failed.txt").write_text("55", encoding="utf-8")
            status = state.Status(folder).load()
            self.assertEqual(status.ids, {33, 44})
            self.assertEqual(status.failed, [55])
            self.assertTrue((folder / "status.json").exists())
            # The folder is kept to osz files + status.json only.
            self.assertFalse((folder / "downloaded_ids.txt").exists())
            self.assertFalse((folder / "failed.txt").exists())

    def test_stale_legacy_files_are_removed_when_status_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "status.json").write_text(
                json.dumps(
                    {
                        "version": 2,
                        "downloaded": {"11": "old"},
                        "failed": [],
                        "titles": {},
                    }
                ),
                encoding="utf-8",
            )
            (folder / "downloaded_ids.txt").write_text("33", encoding="utf-8")
            (folder / "failed.txt").write_text("55", encoding="utf-8")
            status = state.Status(folder).load()
            self.assertEqual(status.ids, {11})
            self.assertFalse((folder / "downloaded_ids.txt").exists())
            self.assertFalse((folder / "failed.txt").exists())

    def test_invalid_json_is_rebuilt(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "status.json").write_text("{nope", encoding="utf-8")
            status = state.Status(folder).load()
            self.assertEqual(status.ids, set())
            self.assertEqual(status.failed, [])


class StatusBehaviourTests(unittest.TestCase):
    def test_success_removes_failure_and_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = state.Status(Path(tmp)).load()
            status.note_failure(1, "Broken")
            status.note_success(1)
            status.flush()
            payload = json.loads((Path(tmp) / "status.json").read_text("utf-8"))
            self.assertEqual(payload["failed"], [])
            self.assertEqual(payload["titles"], {})
            self.assertEqual(payload["downloaded"]["1"] != "", True)

    def test_prune_failed_drops_present_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = state.Status(Path(tmp)).load()
            status.note_failure(1, "One")
            status.note_failure(2, "Two")
            status.prune_failed({2})
            self.assertEqual(status.failed, [1])
            self.assertEqual(status.titles, {"1": "One"})

    def test_batched_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            status = state.Status(folder).load()
            status._last_save = time.monotonic()
            with patch.object(state, "SAVE_EVERY", 2), patch.object(
                state, "SAVE_INTERVAL", 9999
            ):
                status.note_success(1)
                self.assertFalse((folder / "status.json").exists())
                status.note_success(2)
            self.assertTrue((folder / "status.json").exists())
            self.assertFalse((folder / "status.json.tmp").exists())

    def test_scan_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "123.osz").write_bytes(b"x")
            (folder / "456 Title.osz").write_bytes(b"x")
            (folder / "789.part").write_bytes(b"x")
            (folder / "notanid.osz").write_bytes(b"x")
            self.assertEqual(state.scan_existing(folder), {123, 456})


if __name__ == "__main__":
    unittest.main()
