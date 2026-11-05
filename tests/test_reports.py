import unittest

from maniadl_core import reports


class FailedEntriesTests(unittest.TestCase):
    def test_entries_are_sorted_and_include_all_links(self):
        entries = reports.failed_entries(
            [22, 11], {22: "Broken [map]", 11: "Other"}
        )
        self.assertEqual([entry["id"] for entry in entries], [11, 22])
        broken = entries[1]
        self.assertEqual(broken["title"], "Broken [map]")
        urls = [url for _name, url in broken["links"]]
        self.assertIn("https://osu.ppy.sh/beatmapsets/22", urls)
        self.assertIn("https://catboy.best/d/22n", urls)
        self.assertIn("https://api.nerinyan.moe/d/22", urls)

    def test_unknown_title(self):
        entries = reports.failed_entries([5], {})
        self.assertEqual(entries[0]["title"], "unknown title")

    def test_links_text_for_clipboard(self):
        entries = reports.failed_entries([22], {22: "Broken"})
        text = reports.links_text(entries)
        self.assertIn("[22] Broken", text)
        self.assertIn("https://osu.ppy.sh/beatmapsets/22", text)
        self.assertIn("https://catboy.best/d/22n", text)

    def test_no_failures(self):
        self.assertEqual(reports.failed_entries([], {}), [])


if __name__ == "__main__":
    unittest.main()
