using ManiaDL.Core.Api;
using ManiaDL.Core.Logging;
using ManiaDL.Core.Progress;
using ManiaDL.Core.Tests.Support;
using Xunit;

namespace ManiaDL.Core.Tests;

// Ported 1:1 from tests/test_progress.py.
public class TaskBoardTests
{
    [Fact]
    public void Tracks_tasks()
    {
        var board = new TaskBoard();
        var id = board.AddTask("123 Title", total: 100);
        board.Update(id, completed: 40);
        board.Update(id, advance: 10);

        var task = board.Snapshot().Tasks[0];
        Assert.Equal(id, task.Id);
        Assert.Equal("123 Title", task.Description);
        Assert.Equal(50, task.Completed);
        Assert.Equal(100, task.Total);

        board.RemoveTask(id);
        Assert.Empty(board.Snapshot().Tasks);
    }

    [Fact]
    public void Unknown_task_is_ignored()
    {
        var board = new TaskBoard();
        board.Update(99, advance: 5);
        Assert.Empty(board.Snapshot().Tasks);
    }

    [Fact]
    public void Reset_clears_everything()
    {
        var board = new TaskBoard();
        board.AddTask("x", total: 1);
        board.SetMessage("working");
        board.Reset();

        var snapshot = board.Snapshot();
        Assert.Empty(snapshot.Tasks);
        Assert.Equal("", snapshot.Message);
    }

    [Fact]
    public void Message_updates_are_visible_in_snapshots()
    {
        var board = new TaskBoard();
        board.SetMessage("Searching... 3");
        Assert.Equal("Searching... 3", board.Snapshot().Message);
    }

    [Fact]
    public async Task Status_sink_receives_search_updates()
    {
        // Python's StatusSink is a small adapter around progress.update(); the
        // C# port passes TaskBoard.SetMessage directly, so the same contract is
        // checked through a captured sink.
        using var tmp = new TempDir();
        var cfg = TestData.Cfg(tmp.Combine("out"));
        var handler = new ScriptedHandler().Json("""
            {"beatmapsets": [], "cursor_string": null}
            """);
        var time = new ManualTimeProvider();
        var last = "";

        await TestClock.AdvanceUntilAsync(
            time,
            new OsuApiClient(new HttpClient(handler), time, new RunLog(time), new Random(1))
                .SearchSetsAsync("token", cfg, message => last = message, CancellationToken.None));

        Assert.StartsWith("Searching...", last);
    }
}
