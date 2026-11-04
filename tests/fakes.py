"""Shared offline fakes for the unit tests."""

from __future__ import annotations

import io
import zipfile


class FakeContent:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    async def iter_chunked(self, size):
        for chunk in self._chunks:
            yield chunk


class FakeResponse:
    def __init__(
        self,
        status=200,
        json_data=None,
        text_data="",
        headers=None,
        chunks=None,
        content_length=None,
    ):
        self.status = status
        self._json = json_data
        self._text = text_data
        self.headers = headers or {}
        self.content = FakeContent(chunks or [])
        self.content_length = (
            content_length
            if content_length is not None
            else sum(len(chunk) for chunk in (chunks or []))
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self._json

    async def text(self):
        return self._text


class FakeSession:
    def __init__(self, get_responses=None, post_responses=None):
        self.get_responses = list(get_responses or [])
        self.post_responses = list(post_responses or [])
        self.get_calls = []
        self.post_calls = []

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        if not self.get_responses:
            raise AssertionError(f"unexpected GET {url}")
        item = self.get_responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        if not self.post_responses:
            raise AssertionError(f"unexpected POST {url}")
        item = self.post_responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeProgress:
    def __init__(self):
        self.tasks = {}
        self.next_id = 1
        self.updates = []

    def add_task(self, description, total=None):
        task_id = self.next_id
        self.next_id += 1
        self.tasks[task_id] = {"description": description, "total": total}
        return task_id

    def update(self, task_id, **kwargs):
        self.updates.append((task_id, kwargs))

    def remove_task(self, task_id):
        self.tasks.pop(task_id, None)


class FakeOverall:
    def __init__(self):
        self.updates = []

    def add_task(self, description, total=None):
        return 1

    def update(self, task_id, **kwargs):
        self.updates.append((task_id, kwargs))


class FakeSpinner:
    def __init__(self):
        self.messages = []

    def update(self, message):
        self.messages.append(message)


def make_osz_bytes(beatmap_name="map.osu", body="osu file format v14"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(beatmap_name, body)
    return buffer.getvalue()
