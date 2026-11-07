import tempfile
import unittest
from pathlib import Path

from maniadl_core import config


def legacy_raw(**overrides):
    raw = {
        "out": str(Path(tempfile.gettempdir()) / "maniadl_out"),
        "statuses": "ranked",
        "keys": "4",
        "min_sr": 4,
        "max_sr": 7,
        "min_favs": 10,
        "sort": "favourites_desc",
        "limit": 50,
        "workers": 4,
        "batch": 20,
    }
    raw.update(overrides)
    return raw


def advanced_raw(**overrides):
    raw = legacy_raw()
    raw.update(
        {
            "advanced": True,
            "query": "camellia",
            "title": "ghost",
            "artist": "",
            "creator": "",
            "source": "",
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
    )
    raw.update(overrides)
    return raw


class CfgFromRawTests(unittest.TestCase):
    def test_old_config_gets_defaults(self):
        cfg = config.cfg_from_raw(legacy_raw())
        self.assertNotIn("safe_mode", cfg)
        self.assertFalse(cfg["advanced"])
        self.assertEqual(cfg["query"], "")
        self.assertEqual(cfg["exclude"], [])
        self.assertEqual(cfg["min_bpm"], 0.0)
        self.assertEqual(cfg["max_bpm"], 9999.0)
        self.assertEqual(cfg["min_notes"], 0)
        self.assertEqual(cfg["max_notes"], 10**9)

    def test_advanced_config(self):
        cfg = config.cfg_from_raw(advanced_raw())
        self.assertTrue(cfg["advanced"])
        self.assertEqual(cfg["query"], "camellia")
        self.assertEqual(cfg["exclude"], ["tv size"])
        self.assertEqual(cfg["genre"], ["electronic"])
        self.assertEqual(cfg["genre_ids"], [10])
        self.assertEqual(cfg["language_ids"], [5])
        self.assertEqual(cfg["query_terms"], ["camellia"])
        self.assertEqual(cfg["min_bpm"], 150.0)
        self.assertEqual(cfg["max_bpm"], 220.0)
        self.assertEqual(cfg["min_length"], 60)
        self.assertEqual(cfg["max_length"], 300)
        self.assertEqual(cfg["min_notes"], 1000)
        self.assertEqual(cfg["max_notes"], 5000)
        self.assertEqual(cfg["ranked_after"], "2020-01-01")
        self.assertEqual(cfg["ranked_before"], "2024-12-31")

    def test_validation(self):
        with self.assertRaises(ValueError):
            config.cfg_from_raw(legacy_raw(min_sr=8, max_sr=4))
        with self.assertRaises(ValueError):
            config.cfg_from_raw(legacy_raw(min_sr=-1))
        with self.assertRaises(ValueError):
            config.cfg_from_raw(advanced_raw(bpm_range="300-100"))
        with self.assertRaises(ValueError):
            config.cfg_from_raw(advanced_raw(genre="drum and bass"))

    def test_partial_genre_names_resolve(self):
        cfg = config.cfg_from_raw(advanced_raw(genre="elec"))
        self.assertEqual(cfg["genre_ids"], [10])

    def test_limits_and_clamps(self):
        cfg = config.cfg_from_raw(
            legacy_raw(workers=999, batch=0, limit=0, min_favs=-5)
        )
        self.assertEqual(cfg["workers"], 32)
        self.assertEqual(cfg["batch"], 1)
        self.assertEqual(cfg["limit"], 1)
        self.assertEqual(cfg["min_favs"], 0)


class MigrationTests(unittest.TestCase):
    def test_migrate_fills_new_keys_only(self):
        saved = {
            "client_id": "1",
            "client_secret": "secret",
            "workers": 9,
            "safe_mode": False,
            "slide_window": True,
        }
        migrated, changed = config.migrate_saved(saved)
        self.assertTrue(changed)
        self.assertEqual(migrated["workers"], 9)
        self.assertNotIn("safe_mode", migrated)
        self.assertNotIn("slide_window", migrated)
        self.assertFalse(migrated["advanced"])
        self.assertEqual(migrated["query"], "")

    def test_migrate_is_idempotent(self):
        saved, _ = config.migrate_saved({})
        _, changed = config.migrate_saved(saved)
        self.assertFalse(changed)


class StatusAllowedTests(unittest.TestCase):
    def test_any_allows_everything(self):
        cfg = config.cfg_from_raw(legacy_raw(statuses="any"))
        self.assertTrue(config.status_allowed(cfg, "graveyard"))

    def test_ranked_includes_approved(self):
        cfg = config.cfg_from_raw(legacy_raw(statuses="ranked"))
        self.assertTrue(config.status_allowed(cfg, "ranked"))
        self.assertTrue(config.status_allowed(cfg, "approved"))
        self.assertFalse(config.status_allowed(cfg, "loved"))


if __name__ == "__main__":
    unittest.main()
