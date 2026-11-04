"""End-to-end orchestration test with a fake HTTP session (no network)."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from maniadl_core import app, mirrors, runtime
from maniadl_core.constants import MIRRORS
from tests.fakes import FakeResponse, FakeSession, make_osz_bytes


class DummyLive:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def start(self, refresh=False):
        pass

    def stop(self):
        pass

    def update(self, renderable, refresh=False):
        pass

    def refresh(self):
        pass


def legacy_saved(folder: Path) -> dict:
    """Only the old config keys, to prove migration still works."""
    return {
        "client_id": "1234",
        "client_secret": "secret",
        "out": str(folder),
        "statuses": "ranked",
        "keys": "4",
        "min_sr": 0,
        "max_sr": 99,
        "min_favs": 0,
        "sort": "favourites_desc",
        "limit": 10,
        "slide_window": False,
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
            with patch.object(app.config, "load_saved", return_value=legacy_saved(folder)), patch.object(
                app.config, "save_saved"
            ), patch.object(app.Confirm, "ask", return_value=True), patch.object(
                app, "batch_pause", return_value=0
            ), patch.object(
                app, "MIN_FREE_GB", 0.0
            ), patch.object(
                mirrors, "MIN_FREE_GB", 0.0
            ), patch(
                "rich.live.Live", DummyLive
            ), patch.object(
                app.aiohttp, "ClientSession", return_value=session
            ), patch.object(
                app.aiohttp, "TCPConnector", return_value=object()
            ), patch.dict(
                os.environ, {"OSU_CLIENT_ID": "", "OSU_CLIENT_SECRET": ""}
            ):
                await app.main()

            self.assertTrue((folder / "123.osz").exists())
            payload = json.loads((folder / "status.json").read_text("utf-8"))
            self.assertEqual(list(payload["downloaded"]), ["123"])
            self.assertEqual(payload["failed"], [])
            self.assertFalse((folder / "failed_links.txt").exists())
            self.assertEqual(runtime.stats["ok"], 1)
            self.assertEqual(runtime.stats["fail"], 0)

            urls = [call[0] for call in session.get_calls]
            self.assertIn(
                "https://osu.ppy.sh/api/v2/beatmapsets/search", urls
            )
            self.assertEqual(session.post_calls[0][0], "https://osu.ppy.sh/oauth/token")

    async def test_all_mirrors_failing_writes_link_report(self):
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
            with patch.object(app.config, "load_saved", return_value=legacy_saved(folder)), patch.object(
                app.config, "save_saved"
            ), patch.object(app.Confirm, "ask", return_value=True), patch.object(
                app, "batch_pause", return_value=0
            ), patch.object(
                app, "MIN_FREE_GB", 0.0
            ), patch.object(
                mirrors, "MIN_FREE_GB", 0.0
            ), patch(
                "rich.live.Live", DummyLive
            ), patch.object(
                app.aiohttp, "ClientSession", return_value=session
            ), patch.object(
                app.aiohttp, "TCPConnector", return_value=object()
            ), patch.dict(
                os.environ, {"OSU_CLIENT_ID": "", "OSU_CLIENT_SECRET": ""}
            ), patch(
                "maniadl_core.mirrors.asyncio.sleep", new=AsyncMock()
            ):
                await app.main()

            self.assertFalse((folder / "456.osz").exists())
            payload = json.loads((folder / "status.json").read_text("utf-8"))
            self.assertEqual(payload["failed"], [456])
            self.assertEqual(payload["titles"], {"456": "Broken"})
            report = (folder / "failed_links.txt").read_text("utf-8")
            self.assertIn("https://osu.ppy.sh/beatmapsets/456", report)
            self.assertEqual(runtime.stats["fail"], 1)


if __name__ == "__main__":
    unittest.main()
