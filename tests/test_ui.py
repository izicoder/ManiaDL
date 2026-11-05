import tempfile
import unittest
from pathlib import Path

from maniadl_core import config, ui


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
        self.assertEqual(ui.range_label(0, 9999, 0, 9999), "any")
        self.assertEqual(ui.range_label(150, 220, 0, 9999), "150-220")
        self.assertEqual(ui.range_label(150, 9999, 0, 9999), ">=150")
        self.assertEqual(ui.range_label(0, 220, 0, 9999), "<=220")
        self.assertEqual(ui.range_label(60, 300, 0, 10**9, "s"), "60-300s")

    def test_date_labels(self):
        self.assertEqual(ui.date_label("", ""), "any")
        self.assertEqual(ui.date_label("2020", "2024"), "2020..2024")
        self.assertEqual(ui.date_label("2020", ""), ">=2020")
        self.assertEqual(ui.date_label("", "2024"), "<=2024")

    def test_keys_label(self):
        self.assertEqual(ui.keys_label(make_cfg(keys="all")), "all")
        self.assertEqual(ui.keys_label(make_cfg(keys="4,7")), "4K, 7K")


class SummaryTests(unittest.TestCase):
    def test_basic_rows_only_when_advanced_off(self):
        rows = dict(ui.summary_rows(make_cfg(advanced=False)))
        self.assertEqual(rows["Status"], "ranked")
        self.assertEqual(rows["Parallel / batch"], "4 / 20")
        self.assertNotIn("Title contains", rows)

    def test_advanced_rows(self):
        rows = dict(ui.summary_rows(make_cfg()))
        self.assertEqual(rows["Title contains"], "ghost")
        self.assertEqual(rows["Genre"], "electronic")
        self.assertEqual(rows["BPM"], "150-220")
        self.assertEqual(rows["Length"], "60-300s")
        self.assertEqual(rows["Notes"], "1000-5000")
        self.assertEqual(rows["Ranked"], "2020-01-01..2024-12-31")
        self.assertEqual(rows["NSFW"], "exclude")

    def test_search_rows(self):
        rows = dict(ui.search_rows(10, 7, make_cfg()))
        self.assertEqual(rows["Matching sets"], "10")
        self.assertEqual(rows["Already downloaded"], "3")
        self.assertEqual(rows["To download"], "7")
        self.assertEqual(rows["Query"], "camellia")


if __name__ == "__main__":
    unittest.main()
