import unittest

from maniadl_core.progress import StatusSink, TaskBoard
from tests.fakes import FakeProgress


class TaskBoardTests(unittest.TestCase):
    def test_tracks_tasks(self):
        board = TaskBoard()
        tid = board.add_task("123 Title", total=100)
        board.update(tid, completed=40)
        board.update(tid, advance=10)
        task = board.snapshot()["tasks"][0]
        self.assertEqual(task["id"], tid)
        self.assertEqual(task["description"], "123 Title")
        self.assertEqual(task["completed"], 50)
        self.assertEqual(task["total"], 100)

        board.remove_task(tid)
        self.assertEqual(board.snapshot()["tasks"], [])

    def test_unknown_task_is_ignored(self):
        board = TaskBoard()
        board.update(99, advance=5)
        self.assertEqual(board.snapshot()["tasks"], [])

    def test_reset_clears_everything(self):
        board = TaskBoard()
        board.add_task("x", total=1)
        board.set_message("working")
        board.reset()
        snapshot = board.snapshot()
        self.assertEqual(snapshot["tasks"], [])
        self.assertEqual(snapshot["message"], "")

    def test_status_sink_works_with_plain_fakes(self):
        fake = FakeProgress()
        sink = StatusSink(fake)
        sink.update("Searching... 3")
        self.assertEqual(sink.last, "Searching... 3")


if __name__ == "__main__":
    unittest.main()
