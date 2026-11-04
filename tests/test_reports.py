import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from maniadl_core import reports, runtime


class FailedLinksTests(unittest.TestCase):
    def test_writes_all_direct_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = reports.write_failed_links(
                folder, [22, 11], {22: "Broken [map]", 11: "Other"}
            )
            self.assertIsNotNone(path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("Count: 2", text)
            self.assertIn("https://osu.ppy.sh/beatmapsets/22", text)
            self.assertIn("https://catboy.best/d/22n", text)
            self.assertIn("https://api.nerinyan.moe/d/22", text)
            self.assertIn("Broken [map]", text)

    def test_no_failures_removes_stale_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            stale = folder / "failed_links.txt"
            stale.write_text("old", encoding="utf-8")
            path = reports.write_failed_links(folder, [], {})
            self.assertIsNone(path)
            self.assertFalse(stale.exists())

    def test_print_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            recording = Console(record=True, width=160, file=io.StringIO())
            with patch.object(runtime, "console", recording):
                reports.print_failed_links(
                    folder, [22], {22: "Broken [map]"}
                )
            output = recording.export_text()
            self.assertIn("Failed downloads", output)
            self.assertIn("osu!", output)
            self.assertIn("catboy", output)

    def test_print_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            recording = Console(record=True, width=160, file=io.StringIO())
            with patch.object(runtime, "console", recording):
                reports.print_failed_links(Path(tmp), [], {})
            self.assertIn("No failed downloads", recording.export_text())


if __name__ == "__main__":
    unittest.main()
