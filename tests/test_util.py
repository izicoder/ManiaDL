import tempfile
import unittest
import zipfile
from pathlib import Path

from maniadl_core import util


class ParseRangeTests(unittest.TestCase):
    def test_blank_means_no_filter(self):
        self.assertEqual(util.parse_range(""), (None, None))
        self.assertEqual(util.parse_range("any"), (None, None))

    def test_pair_and_operators(self):
        self.assertEqual(util.parse_range("150-220"), (150.0, 220.0))
        self.assertEqual(util.parse_range("150..220"), (150.0, 220.0))
        self.assertEqual(util.parse_range("150 to 220"), (150.0, 220.0))
        self.assertEqual(util.parse_range(">=150"), (150.0, None))
        self.assertEqual(util.parse_range("<=220"), (None, 220.0))
        self.assertEqual(util.parse_range("180"), (180.0, 180.0))
        self.assertEqual(util.parse_range("=180"), (180.0, 180.0))

    def test_int_cast(self):
        self.assertEqual(util.parse_range("60-300", int), (60, 300))

    def test_invalid_and_inverted(self):
        with self.assertRaises(ValueError):
            util.parse_range("nope")
        with self.assertRaises(ValueError):
            util.parse_range("300-60")
        with self.assertRaises(ValueError):
            util.parse_range("-1", minimum=0)


class ParseDateRangeTests(unittest.TestCase):
    def test_blank(self):
        self.assertEqual(util.parse_date_range(""), (None, None))

    def test_ranges_and_normalisation(self):
        self.assertEqual(
            util.parse_date_range("2020-1..2024-2"), ("2020-01", "2024-02")
        )
        self.assertEqual(
            util.parse_date_range("2020/01/02..2020/12/31"),
            ("2020-01-02", "2020-12-31"),
        )
        self.assertEqual(util.parse_date_range("2020..2024"), ("2020", "2024"))
        self.assertEqual(util.parse_date_range(">=2020"), ("2020", None))
        self.assertEqual(util.parse_date_range("<=2024"), (None, "2024"))

    def test_invalid(self):
        with self.assertRaises(ValueError):
            util.parse_date_range("not-a-date")
        with self.assertRaises(ValueError):
            util.parse_date_range("2024..2020")


class ParseListsTests(unittest.TestCase):
    def test_statuses(self):
        self.assertEqual(util.parse_statuses("ranked,loved"), ["ranked", "loved"])
        self.assertEqual(util.parse_statuses("any,ranked"), ["any"])
        self.assertEqual(util.parse_statuses("ranked,ranked"), ["ranked"])
        with self.assertRaises(ValueError):
            util.parse_statuses("ranked,wat")

    def test_keys(self):
        self.assertIsNone(util.parse_keys("all"))
        self.assertEqual(util.parse_keys("4, 7 4"), [4, 7])
        with self.assertRaises(ValueError):
            util.parse_keys("0")
        with self.assertRaises(ValueError):
            util.parse_keys("19")

    def test_csv(self):
        self.assertEqual(util.parse_csv("Anime, Video Game;Rock"), ["anime", "video game", "rock"])


class QueryTermTests(unittest.TestCase):
    def test_plain_text_is_client_filtered(self):
        self.assertEqual(
            util.simple_query_terms("Camellia ghost"), ["camellia", "ghost"]
        )

    def test_operator_queries_are_left_to_api(self):
        self.assertEqual(util.simple_query_terms("stars>=5"), [])
        self.assertEqual(util.simple_query_terms("title=ghost"), [])
        self.assertEqual(util.simple_query_terms("keys:4"), [])


class MiscUtilTests(unittest.TestCase):
    def test_direct_links_are_unique(self):
        links = util.direct_links(123)
        urls = [url for _, url in links]
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(links[0][0], "osu!")
        self.assertTrue(any(name == "catboy" for name, _ in links))

    def test_valid_osz(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.osz"
            with zipfile.ZipFile(good, "w") as archive:
                archive.writestr("map.osu", "osu file format v14")
            bad = Path(tmp) / "bad.osz"
            bad.write_text("<html>not a zip</html>", encoding="utf-8")
            no_map = Path(tmp) / "no_map.osz"
            with zipfile.ZipFile(no_map, "w") as archive:
                archive.writestr("audio.mp3", b"123")
            self.assertTrue(util.valid_osz(good))
            self.assertFalse(util.valid_osz(bad))
            self.assertFalse(util.valid_osz(no_map))

    def test_retry_after(self):
        self.assertEqual(util.retry_after({"Retry-After": "12"}), 12)
        self.assertEqual(util.retry_after({}, default=7), 7)
        self.assertGreaterEqual(util.retry_after({"Retry-After": "9999"}), 1)
        self.assertLessEqual(util.retry_after({"Retry-After": "9999"}), 300)

    def test_free_gb_returns_number(self):
        self.assertIsInstance(util.free_gb(Path.cwd()), float)

    def test_mirror_helpers(self):
        self.assertEqual(
            util.mirror_host("https://catboy.best/d/{id}"), "catboy.best"
        )
        self.assertEqual(
            util.mirror_headers("https://catboy.best/d/1"),
            {"Referer": "https://catboy.best/"},
        )


if __name__ == "__main__":
    unittest.main()
