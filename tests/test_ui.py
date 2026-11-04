import io
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from maniadl_core import app, config, runtime, ui


def make_cfg(**overrides):
    raw = {
        "out": str(Path(tempfile.gettempdir()) / "maniadl_ui_test"),
        "statuses": "ranked",
        "keys": "4",
        "min_sr": 4,
        "max_sr": 7,
        "min_favs": 10,
        "sort": "favourites_desc",
        "limit": 50,
        "workers": 4,
        "batch": 20,
        "advanced": True,
        "query": "camellia",
        "title": "ghost",
        "artist": "camellia",
        "creator": "mapper",
        "source": "game",
        "exclude": "tv size",
        "genre": "electronic",
        "language": "instrumental",
        "bpm_range": "150-220",
        "length_range": "60-300",
        "notes_range": "1000-5000",
        "min_plays": 100,
        "ranked_range": "2020-01-01..2024-12-31",
        "include_nsfw": False,
    }
    raw.update(overrides)
    return config.cfg_from_raw(raw)


class LabelTests(unittest.TestCase):
    def test_range_labels(self):
        self.assertEqual(ui._range_label(0, 9999, 0, 9999), "any")
        self.assertEqual(ui._range_label(150, 220, 0, 9999), "150-220")
        self.assertEqual(ui._range_label(150, 9999, 0, 9999), ">=150")
        self.assertEqual(ui._range_label(0, 220, 0, 9999), "<=220")
        self.assertEqual(ui._range_label(60, 300, 0, 10**9, "s"), "60-300s")

    def test_date_labels(self):
        self.assertEqual(ui._date_label("", ""), "any")
        self.assertEqual(ui._date_label("2020", "2024"), "2020..2024")
        self.assertEqual(ui._date_label("2020", ""), ">=2020")
        self.assertEqual(ui._date_label("", "2024"), "<=2024")


class AskConfigTests(unittest.TestCase):
    def _saved(self):
        return {
            "out": "C:/tmp/m",
            "statuses": "ranked",
            "keys": "4",
            "min_sr": 1,
            "max_sr": 10,
            "min_favs": 1,
            "sort": "favourites_desc",
            "limit": 100,
            "workers": 4,
            "batch": 16,
            "advanced": True,
            "query": "pack",
            "title": "pack",
            "artist": "artist",
            "creator": "mapper",
            "source": "game",
            "exclude": "tv",
            "genre": "electronic",
            "language": "instrumental",
            "bpm_range": "150-220",
            "length_range": "60-300",
            "notes_range": "1000-5000",
            "min_plays": 10,
            "ranked_range": "2020..2024",
            "include_nsfw": True,
        }

    def _ask(self, confirm_answers):
        with patch.object(ui.Prompt, "ask", return_value="") as prompt, patch.object(
            ui.IntPrompt, "ask", return_value=0
        ), patch.object(ui.FloatPrompt, "ask", return_value=0.0), patch.object(
            ui.Confirm, "ask", side_effect=confirm_answers
        ):
            cfg, raw = ui.ask_config(self._saved())
        return cfg, raw, prompt

    def test_reset_clears_advanced_values(self):
        cfg, raw, _ = self._ask([True, True, False])
        self.assertEqual(raw["query"], "")
        self.assertEqual(raw["title"], "")
        self.assertEqual(raw["exclude"], "")
        self.assertEqual(raw["bpm_range"], "")
        self.assertEqual(raw["min_plays"], 0)
        self.assertFalse(raw["include_nsfw"])
        self.assertEqual(cfg["query"], "")
        self.assertEqual(cfg["genre"], [])

    def test_no_reset_keeps_old_values_as_defaults(self):
        _, _, prompt = self._ask([False, True, True])
        defaults = {
            call.args[0]: call.kwargs.get("default")
            for call in prompt.call_args_list
        }
        self.assertEqual(
            defaults["osu! search query / free text "
                     "(supports stars>=5, keys=4, title=..., ranked>=2020)"],
            "pack",
        )
        self.assertEqual(defaults["Title contains"], "pack")
        self.assertEqual(defaults["Genres (comma-separated, partial ok, blank=any)"],
                         "electronic")


class RenderingTests(unittest.TestCase):
    def setUp(self):
        runtime.reset_run()

    def test_summary_includes_advanced_filters(self):
        recording = Console(record=True, width=160, file=io.StringIO())
        with patch.object(runtime, "console", recording):
            ui.show_summary(make_cfg())
        output = recording.export_text()
        self.assertIn("Settings", output)
        self.assertIn("Title contains", output)
        self.assertIn("BPM", output)

    def test_search_summary(self):
        recording = Console(record=True, width=160, file=io.StringIO())
        with patch.object(runtime, "console", recording):
            ui.show_search_summary(
                [{"id": 1}, {"id": 2}], [{"id": 2}], {1}, make_cfg()
            )
        output = recording.export_text()
        self.assertIn("Matching sets", output)
        self.assertIn("To download", output)

    def test_dashboard_components(self):
        runtime.stats.update(ok=1, fail=2, active=3, bytes=1_000_000)
        panel = ui.stats_panel(make_cfg(), time.time() - 2)
        self.assertIsNotNone(panel)
        table = ui.mirror_table()
        self.assertEqual(len(table.rows), len(runtime.mstats))
        progress, overall = ui.make_progress()
        self.assertIsNotNone(progress)
        self.assertIsNotNone(overall)


class BatchPauseTests(unittest.TestCase):
    def test_pause_scales_with_workers(self):
        cfg = make_cfg(workers=1)
        self.assertGreaterEqual(app.batch_pause(cfg), 3.0)
        cfg = make_cfg(workers=8)
        self.assertGreaterEqual(app.batch_pause(cfg), 4.0)


if __name__ == "__main__":
    unittest.main()
