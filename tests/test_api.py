import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from maniadl_core import api, config
from maniadl_core.constants import GENRE_IDS, LANGUAGE_IDS
from tests.fakes import FakeResponse, FakeSession, FakeSpinner


def make_cfg(**overrides):
    raw = {
        "out": str(Path(tempfile.gettempdir()) / "maniadl_api_test"),
        "statuses": "ranked",
        "keys": "all",
        "min_sr": 0,
        "max_sr": 99,
        "min_favs": 0,
        "sort": "favourites_desc",
        "limit": 10,
        "workers": 1,
        "batch": 1,
    }
    raw.update(overrides)
    return config.cfg_from_raw(raw)


def make_set(
    sid=1,
    status="ranked",
    keys=4,
    stars=5.0,
    title="Ghost",
    artist="Camellia",
    creator="Mapper",
    favourite_count=100,
    play_count=500,
    bpm=180,
    length=200,
    notes=2000,
    ranked_date="2023-05-01T00:00:00+00:00",
    genre="Electronic",
    language="Instrumental",
    nsfw=False,
    tags="electronic instrumental",
):
    return {
        "id": sid,
        "title": title,
        "title_unicode": title,
        "artist": artist,
        "artist_unicode": artist,
        "creator": creator,
        "source": "Game",
        "tags": tags,
        "status": status,
        "favourite_count": favourite_count,
        "play_count": play_count,
        "nsfw": nsfw,
        "bpm": bpm,
        "genre_id": GENRE_IDS.get(genre.lower()),
        "language_id": LANGUAGE_IDS.get(language.lower()),
        "genre": {"name": genre},
        "language": {"name": language},
        "ranked_date": ranked_date,
        "beatmaps": [
            {
                "mode_int": 3,
                "cs": keys,
                "difficulty_rating": stars,
                "count_circles": notes,
                "count_sliders": 0,
                "count_spinners": 0,
                "total_length": length,
                "version": "Insane",
            }
        ],
    }


class BuildQueryTests(unittest.TestCase):
    def test_legacy_defaults_do_not_add_filters(self):
        cfg = make_cfg()
        self.assertEqual(api.build_query(cfg, None), "")
        self.assertEqual(api.minimal_query(cfg, None), "")

    def test_advanced_query(self):
        cfg = make_cfg(
            advanced=True,
            query="camellia",
            title="ghost",
            artist="camellia",
            creator="mapper",
            source="game",
            min_sr=4,
            max_sr=7,
            min_favs=10,
            bpm_range="150-220",
            length_range="60-300",
            ranked_range="2020-01-01..2024-12-31",
        )
        query = api.build_query(cfg, 4)
        for part in (
            "camellia",
            "ghost",
            "mapper",
            "game",
            "keys=4",
            "stars>=4",
            "stars<=7",
            "favourites>=10",
            "bpm>=150",
            "bpm<=220",
            "length>=60",
            "length<=300",
            "ranked>=2020-01-01",
            "ranked<=2024-12-31",
        ):
            self.assertIn(part, query)

    def test_minimal_query(self):
        cfg = make_cfg(advanced=True, query="camellia", title="ghost")
        self.assertEqual(api.minimal_query(cfg, 7), "camellia keys=7")

    def test_search_params_narrows_genre_and_language(self):
        cfg = make_cfg(advanced=True, genre="electronic", language="instrumental")
        params = api.search_params(cfg, 4)
        self.assertEqual(params["g"], "10")
        self.assertEqual(params["l"], "5")
        self.assertIn("keys=4", params["q"])

    def test_search_params_keeps_multiple_genres_client_side(self):
        cfg = make_cfg(advanced=True, genre="electronic, rock")
        params = api.search_params(cfg, None)
        self.assertNotIn("g", params)
        self.assertEqual(cfg["genre_ids"], [4, 10])


class QualifiesTests(unittest.TestCase):
    def test_basic_match(self):
        cfg = make_cfg(keys="4", min_sr=4, max_sr=7, min_favs=10)
        self.assertTrue(api.qualifies(make_set(), cfg))

    def test_status_and_favourites(self):
        cfg = make_cfg(min_favs=10)
        self.assertTrue(api.qualifies(make_set(status="approved"), cfg))
        self.assertFalse(api.qualifies(make_set(status="loved"), cfg))
        self.assertFalse(api.qualifies(make_set(favourite_count=0), cfg))

    def test_keys_and_stars(self):
        cfg = make_cfg(keys="7", min_sr=4, max_sr=7)
        self.assertFalse(api.qualifies(make_set(keys=4), cfg))
        self.assertTrue(api.qualifies(make_set(keys=7), cfg))
        self.assertFalse(api.qualifies(make_set(stars=9), cfg))

    def test_text_filters(self):
        cfg = make_cfg(
            advanced=True, title="ghost", artist="camellia", creator="mapper"
        )
        self.assertTrue(api.qualifies(make_set(), cfg))
        self.assertFalse(api.qualifies(make_set(title="Other"), cfg))
        self.assertFalse(api.qualifies(make_set(artist="Other"), cfg))
        self.assertFalse(api.qualifies(make_set(creator="Other"), cfg))

    def test_free_query_and_exclude(self):
        cfg = make_cfg(advanced=True, query="camellia ghost", exclude="tv size")
        self.assertTrue(api.qualifies(make_set(), cfg))
        self.assertFalse(api.qualifies(make_set(artist="Other"), cfg))
        self.assertFalse(
            api.qualifies(make_set(tags="electronic instrumental tv size"), cfg)
        )

    def test_genre_language_bpm_length_notes_plays_dates(self):
        cfg = make_cfg(
            advanced=True,
            genre="electronic",
            language="instrumental",
            bpm_range="150-220",
            length_range="60-300",
            notes_range="1000-5000",
            min_plays=100,
            ranked_range="2020-01-01..2024-12-31",
        )
        self.assertTrue(api.qualifies(make_set(), cfg))
        self.assertFalse(api.qualifies(make_set(genre="Rock"), cfg))
        self.assertFalse(api.qualifies(make_set(language="English"), cfg))
        self.assertFalse(api.qualifies(make_set(bpm=300), cfg))
        self.assertFalse(api.qualifies(make_set(length=30), cfg))
        self.assertFalse(api.qualifies(make_set(notes=100), cfg))
        self.assertFalse(api.qualifies(make_set(play_count=0), cfg))
        self.assertFalse(api.qualifies(make_set(ranked_date=None), cfg))

    def test_length_applies_to_matching_diff(self):
        cfg = make_cfg(advanced=True, length_range="60-300")
        data = make_set()
        data["beatmaps"][0]["total_length"] = 30
        data["beatmaps"].append(
            {
                "mode_int": 3,
                "cs": 4,
                "difficulty_rating": 5.0,
                "count_circles": 2000,
                "count_sliders": 0,
                "count_spinners": 0,
                "total_length": 500,
                "version": "Another",
            }
        )
        self.assertFalse(api.qualifies(data, cfg))
        data["beatmaps"][0]["total_length"] = 200
        self.assertTrue(api.qualifies(data, cfg))

    def test_nsfw_filter(self):
        cfg = make_cfg()
        self.assertFalse(api.qualifies(make_set(nsfw=True), cfg))
        cfg = make_cfg(advanced=True, include_nsfw=True)
        self.assertTrue(api.qualifies(make_set(nsfw=True), cfg))

    def test_genre_and_language_use_api_ids(self):
        """Search responses carry ids, not name objects."""
        cfg = make_cfg(advanced=True, genre="electronic", language="instrumental")
        data = make_set()
        data.pop("genre")
        data.pop("language")
        self.assertTrue(api.qualifies(data, cfg))

        data["genre_id"] = GENRE_IDS["rock"]
        self.assertFalse(api.qualifies(data, cfg))

    def test_unknown_genre_is_rejected_at_parse_time(self):
        with self.assertRaises(ValueError):
            make_cfg(advanced=True, genre="drum and bass")


class SearchOneTests(unittest.IsolatedAsyncioTestCase):
    async def test_paginates_and_filters(self):
        cfg = make_cfg(keys="4", min_sr=4, max_sr=7)
        page_one = FakeResponse(
            json_data={
                "beatmapsets": [make_set(1), make_set(2, status="loved")],
                "cursor_string": "cursor-1",
            }
        )
        page_two = FakeResponse(
            json_data={"beatmapsets": [make_set(3)], "cursor_string": None}
        )
        session = FakeSession([page_one, page_two])
        found = {}
        spinner = FakeSpinner()

        with patch("maniadl_core.api.search_delay", return_value=0):
            await api.search_one(
                session, {}, {"m": "3"}, cfg, found, spinner
            )

        self.assertEqual(set(found), {1, 3})
        self.assertEqual(len(session.get_calls), 2)
        self.assertEqual(
            session.get_calls[1][1]["params"]["cursor_string"], "cursor-1"
        )
        self.assertTrue(spinner.messages)

    async def test_http_400_raises_search_rejected(self):
        session = FakeSession([FakeResponse(status=400, text_data="bad query")])
        with self.assertRaises(api.SearchRejected):
            await api.search_one(
                session, {}, {"m": "3"}, make_cfg(), {}, FakeSpinner()
            )

    async def test_429_waits_and_retries(self):
        session = FakeSession(
            [
                FakeResponse(status=429, headers={"Retry-After": "1"}),
                FakeResponse(json_data={"beatmapsets": [], "cursor_string": None}),
            ]
        )
        with patch("maniadl_core.api.search_delay", return_value=0), patch(
            "maniadl_core.api.asyncio.sleep", new=AsyncMock()
        ):
            await api.search_one(
                session, {}, {"m": "3"}, make_cfg(), {}, FakeSpinner()
            )
        self.assertEqual(len(session.get_calls), 2)


class SearchSetsFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_falls_back_when_advanced_query_is_rejected(self):
        cfg = make_cfg(
            advanced=True, query="camellia", keys="4", min_sr=4, max_sr=7
        )
        session = FakeSession(
            [
                FakeResponse(status=400, text_data="bad query"),
                FakeResponse(
                    json_data={
                        "beatmapsets": [make_set(1)],
                        "cursor_string": None,
                    }
                ),
            ]
        )
        with patch("maniadl_core.api.search_delay", return_value=0):
            sets = await api.search_sets(
                session, "token", cfg, FakeSpinner()
            )
        self.assertEqual([item["id"] for item in sets], [1])
        self.assertEqual(len(session.get_calls), 2)
        self.assertIn("camellia", session.get_calls[1][1]["params"]["q"])


class SearchPacerTests(unittest.IsolatedAsyncioTestCase):
    async def test_second_request_waits_for_the_interval(self):
        pacer = api.SearchPacer(interval=5.0)
        with patch("maniadl_core.api.asyncio.sleep", new=AsyncMock()) as sleep, patch(
            "maniadl_core.api.search_delay", return_value=5.0
        ):
            await pacer.wait()
            sleep.assert_not_called()
            await pacer.wait()
            sleep.assert_awaited_once()

    async def test_rate_limit_stretches_then_recovers(self):
        pacer = api.SearchPacer(interval=1.0)
        pacer.penalise(12)
        self.assertEqual(pacer.interval, 12.0)
        for _ in range(40):
            pacer.success()
        self.assertEqual(pacer.interval, 1.0)


class SearchParamRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_genre_and_language_are_sent_as_api_params(self):
        cfg = make_cfg(advanced=True, genre="electronic", language="instrumental")
        session = FakeSession(
            [FakeResponse(json_data={"beatmapsets": [], "cursor_string": None})]
        )
        with patch("maniadl_core.api.search_delay", return_value=0):
            await api.search_sets(session, "token", cfg, FakeSpinner())
        params = session.get_calls[0][1]["params"]
        self.assertEqual(params["g"], "10")
        self.assertEqual(params["l"], "5")


if __name__ == "__main__":
    unittest.main()
