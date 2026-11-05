import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiohttp

from maniadl_core import mirrors, runtime, state, util
from maniadl_core.constants import MIRRORS
from tests.fakes import FakeOverall, FakeProgress, FakeResponse, FakeSession, make_osz_bytes


def make_cfg(folder: Path):
    return {
        "out": folder,
        "workers": 1,
        "batch": 1,
    }


class FetchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        runtime.reset_run()

    async def test_downloads_to_part_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            part = Path(tmp) / "1.part"
            session = FakeSession(
                [FakeResponse(chunks=[b"hello ", b"world"])]
            )
            progress = FakeProgress()
            tid = progress.add_task("test")
            await mirrors.fetch(
                session, "https://catboy.best/d/1", part, progress, tid
            )
            self.assertEqual(part.read_bytes(), b"hello world")
            self.assertEqual(runtime.stats["bytes"], 11)
            self.assertEqual(
                session.get_calls[0][1]["headers"]["Referer"],
                "https://catboy.best/",
            )

    async def test_resumes_with_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            part = Path(tmp) / "1.part"
            part.write_bytes(b"abc")
            session = FakeSession(
                [
                    FakeResponse(
                        status=206,
                        headers={"Content-Range": "bytes 3-5/6"},
                        chunks=[b"def"],
                        content_length=3,
                    )
                ]
            )
            progress = FakeProgress()
            tid = progress.add_task("test")
            await mirrors.fetch(
                session, "https://catboy.best/d/1", part, progress, tid
            )
            self.assertEqual(part.read_bytes(), b"abcdef")
            self.assertEqual(
                session.get_calls[0][1]["headers"]["Range"], "bytes=3-"
            )

    async def test_rate_limit_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = FakeSession(
                [FakeResponse(status=429, headers={"Retry-After": "7"})]
            )
            progress = FakeProgress()
            tid = progress.add_task("test")
            with self.assertRaises(mirrors.RateLimited) as caught:
                await mirrors.fetch(
                    session,
                    "https://catboy.best/d/1",
                    Path(tmp) / "1.part",
                    progress,
                    tid,
                )
            self.assertEqual(caught.exception.seconds, 7)

    async def test_mirror_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = FakeSession([FakeResponse(status=404)])
            progress = FakeProgress()
            tid = progress.add_task("test")
            with self.assertRaises(mirrors.MirrorMiss):
                await mirrors.fetch(
                    session,
                    "https://catboy.best/d/1",
                    Path(tmp) / "1.part",
                    progress,
                    tid,
                )

    async def test_stop_aborts_transfer(self):
        with tempfile.TemporaryDirectory() as tmp:
            part = Path(tmp) / "1.part"
            session = FakeSession([FakeResponse(chunks=[b"hello"])])
            progress = FakeProgress()
            tid = progress.add_task("test")
            runtime.request_stop()
            try:
                with self.assertRaises(mirrors.Stopped):
                    await mirrors.fetch(
                        session,
                        "https://catboy.best/d/1",
                        part,
                        progress,
                        tid,
                    )
            finally:
                runtime.reset_run()

    async def test_bad_content_range_restarts(self):
        with tempfile.TemporaryDirectory() as tmp:
            part = Path(tmp) / "1.part"
            part.write_bytes(b"abc")
            session = FakeSession(
                [
                    FakeResponse(
                        status=206,
                        headers={"Content-Range": "bytes 0-2/6"},
                        chunks=[b"def"],
                        content_length=3,
                    )
                ]
            )
            progress = FakeProgress()
            tid = progress.add_task("test")
            with self.assertRaises(aiohttp.ClientError):
                await mirrors.fetch(
                    session, "https://catboy.best/d/1", part, progress, tid
                )
            self.assertFalse(part.exists())


class ChooseMirrorTests(unittest.TestCase):
    def setUp(self):
        runtime.reset_run()

    def test_returns_a_ready_mirror(self):
        mirror, wait = mirrors.choose_mirror(0)
        self.assertIsNotNone(mirror)
        self.assertEqual(wait, 0.0)
        self.assertIn(mirror[0], {name for name, _ in MIRRORS})

    def test_all_cooling_returns_wait(self):
        future = 9_999_999_999.0
        for name, _ in MIRRORS:
            runtime.mstats[name]["until"] = future
        mirror, wait = mirrors.choose_mirror(0)
        self.assertIsNone(mirror)
        self.assertGreater(wait, 0)

    def test_tried_mirrors_are_skipped(self):
        tried = {name for name, _ in MIRRORS}
        mirror, wait = mirrors.choose_mirror(0, tried)
        self.assertIsNone(mirror)
        self.assertEqual(wait, 0.0)

    def test_park_host_parks_every_endpoint_on_that_host(self):
        mirrors.park_host("https://catboy.best/d/{id}", 60)
        self.assertGreater(runtime.mstats["catboy"]["until"], 0)
        self.assertGreater(runtime.mstats["catboy-video"]["until"], 0)
        self.assertEqual(runtime.mstats["nerinyan"]["until"], 0)


class DownloadSetTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            cfg = make_cfg(folder)
            runtime.reset_run()
            status = state.Status(folder).load()
            data = make_osz_bytes()
            session = FakeSession(
                [FakeResponse(chunks=[data], content_length=len(data))]
            )
            progress = FakeProgress()
            overall = FakeOverall()
            failed = {}
            await mirrors.download_set(
                session,
                {"id": 123, "title": "Test"},
                cfg,
                progress,
                overall,
                1,
                asyncio.Semaphore(1),
                failed,
                status,
            )
            self.assertTrue((folder / "123.osz").exists())
            self.assertEqual(status.ids, {123})
            self.assertEqual(runtime.stats["ok"], 1)
            self.assertEqual(failed, {})
            self.assertEqual(overall.updates, [(1, {"advance": 1})])

    async def test_all_mirrors_missing_marks_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            cfg = make_cfg(folder)
            runtime.reset_run()
            status = state.Status(folder).load()
            session = FakeSession(
                [FakeResponse(status=404) for _ in range(len(MIRRORS))]
            )
            progress = FakeProgress()
            overall = FakeOverall()
            failed = {}
            await mirrors.download_set(
                session,
                {"id": 456, "title": "Broken"},
                cfg,
                progress,
                overall,
                1,
                asyncio.Semaphore(1),
                failed,
                status,
            )
            self.assertFalse((folder / "456.osz").exists())
            self.assertEqual(status.failed, [456])
            self.assertEqual(failed, {456: "Broken"})
            self.assertEqual(runtime.stats["fail"], 1)

    async def test_invalid_zip_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            cfg = make_cfg(folder)
            runtime.reset_run()
            status = state.Status(folder).load()
            session = FakeSession(
                [FakeResponse(chunks=[b"<html>nope</html>"])]
                * len(MIRRORS)
            )
            progress = FakeProgress()
            overall = FakeOverall()
            failed = {}
            with patch(
                "maniadl_core.mirrors.asyncio.sleep", new=AsyncMock()
            ):
                await mirrors.download_set(
                    session,
                    {"id": 789, "title": "Bad"},
                    cfg,
                    progress,
                    overall,
                    1,
                    asyncio.Semaphore(1),
                    failed,
                    status,
                )
            self.assertFalse((folder / "789.osz").exists())
            self.assertEqual(failed, {789: "Bad"})


if __name__ == "__main__":
    unittest.main()
