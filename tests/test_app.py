"""End-to-end orchestration test with a fake HTTP session (no network)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from maniadl_core import app, config, mirrors, runtime
from maniadl_core.constants import MIRRORS
from maniadl_core.progress import TaskBoard
from tests.fakes import FakeResponse, FakeSession, make_osz_bytes


def raw_config(folder: Path) -> dict:
    """Only the old config keys, to prove migration still works."""
    return {
        "out": str(folder),
        "statuses": "ranked",
        "keys": "4",
        "min_sr": 0,
        "max_sr": 99,
        "min_favs": 0,
        "sort": "favourites_desc",
        "limit": 10,
        "workers": 1,
        "batch": 5,
    }


def make_set(sid=123, title="Test Set"):
    return {
        "id": sid,
        "title": title,
        "title_unicode": title,
        "artist": "Artist",
        "artist_unicode": "Artist",
        "creator": "Mapper",
        "source": "",
        "tags": "mania",
        "status": "ranked",
        "favourite_count": 10,
        "play_count": 100,
        "nsfw": False,
        "bpm": 180,
        "genre": {"name": "Electronic"},
        "language": {"name": "Instrumental"},
        "ranked_date": "2023-01-01T00:00:00+00:00",
        "beatmaps": [
            {
                "mode_int": 3,
                "cs": 4,
                "difficulty_rating": 5.0,
                "count_circles": 2000,
                "count_sliders": 0,
                "count_spinners": 0,
                "total_length": 200,
                "version": "Insane",
            }
        ],
    }


class MainFlowTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, folder: Path, session: FakeSession) -> dict:
        cfg = config.cfg_from_raw(raw_config(folder))
        with patch.object(app, "batch_pause", return_value=0), patch.object(app, "MIN_FREE_GB", 0.0), patch.object(
            mirrors, "MIN_FREE_GB", 0.0
        ), patch.object(
            app.aiohttp, "ClientSession", return_value=session
        ), patch.object(
            app.aiohttp, "TCPConnector", return_value=object()
        ):
            return await app.run(
                cfg, "1234", "secret", TaskBoard(), TaskBoard()
            )

    async def test_full_run_downloads_and_records_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            data = make_osz_bytes()
            session = FakeSession(
                get_responses=[
                    FakeResponse(
                        json_data={
                            "beatmapsets": [make_set()],
                            "cursor_string": None,
                        }
                    ),
                    FakeResponse(chunks=[data], content_length=len(data)),
                ],
                post_responses=[
                    FakeResponse(json_data={"access_token": "token"})
                ],
            )
            result = await self._run(folder, session)

            self.assertTrue((folder / "123.osz").exists())
            payload = json.loads((folder / "status.json").read_text("utf-8"))
            self.assertEqual(list(payload["downloaded"]), ["123"])
            self.assertEqual(payload["failed"], [])
            self.assertFalse((folder / "failed_links.txt").exists())
            self.assertEqual(runtime.stats["ok"], 1)
            self.assertEqual(runtime.stats["fail"], 0)
            self.assertEqual(result["matched"], 1)
            self.assertEqual(result["todo"], 1)
            self.assertEqual(result["failed"], {})

            urls = [call[0] for call in session.get_calls]
            self.assertIn(
                "https://osu.ppy.sh/api/v2/beatmapsets/search", urls
            )
            self.assertEqual(
                session.post_calls[0][0], "https://osu.ppy.sh/oauth/token"
            )

    async def test_all_mirrors_failing_keeps_links_in_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            session = FakeSession(
                get_responses=[
                    FakeResponse(
                        json_data={
                            "beatmapsets": [make_set(456, "Broken")],
                            "cursor_string": None,
                        }
                    ),
                    *[FakeResponse(status=404) for _ in range(len(MIRRORS))],
                ],
                post_responses=[
                    FakeResponse(json_data={"access_token": "token"})
                ],
            )
            with patch(
                "maniadl_core.mirrors.asyncio.sleep", new=AsyncMock()
            ):
                result = await self._run(folder, session)

            self.assertFalse((folder / "456.osz").exists())
            payload = json.loads((folder / "status.json").read_text("utf-8"))
            self.assertEqual(payload["failed"], [456])
            self.assertEqual(payload["titles"], {"456": "Broken"})
            self.assertFalse((folder / "failed_links.txt").exists())
            self.assertEqual(result["failed"], {456: "Broken"})
            self.assertEqual(runtime.stats["fail"], 1)

    async def test_stale_link_report_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "failed_links.txt").write_text("old", encoding="utf-8")
            session = FakeSession(
                get_responses=[
                    FakeResponse(
                        json_data={
                            "beatmapsets": [make_set()],
                            "cursor_string": None,
                        }
                    ),
                    FakeResponse(
                        chunks=[make_osz_bytes()],
                        content_length=len(make_osz_bytes()),
                    ),
                ],
                post_responses=[
                    FakeResponse(json_data={"access_token": "token"})
                ],
            )
            await self._run(folder, session)
            self.assertFalse((folder / "failed_links.txt").exists())

    async def test_log_listener_receives_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            data = make_osz_bytes()
            session = FakeSession(
                get_responses=[
                    FakeResponse(
                        json_data={
                            "beatmapsets": [make_set()],
                            "cursor_string": None,
                        }
                    ),
                    FakeResponse(chunks=[data], content_length=len(data)),
                ],
                post_responses=[
                    FakeResponse(json_data={"access_token": "token"})
                ],
            )
            lines = []
            runtime.set_log_listener(lines.append)
            try:
                await self._run(folder, session)
            finally:
                runtime.set_log_listener(None)
            joined = "\n".join(lines)
            self.assertIn("Search finished", joined)
            self.assertIn("123 via", joined)


if __name__ == "__main__":
    unittest.main()
