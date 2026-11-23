using System.Text;
using ManiaDL.Core.Config;
using ManiaDL.Core.Constants;
using ManiaDL.Core.Logging;
using ManiaDL.Core.Mirrors;
using ManiaDL.Core.Progress;
using ManiaDL.Core.Run;
using ManiaDL.Core.State;
using ManiaDL.Core.Tests.Support;
using ManiaDL.Core.Util;
using Xunit;

namespace ManiaDL.Core.Tests;

// Ported 1:1 from tests/test_mirrors.py.
public class FetchTests
{
    private static RunContext NewContext(TimeProvider time) =>
        new(new CancellationTokenSource(), new RunLog(time), new TaskBoard(), time, new Random(1))
        {
            MinFreeGb = 0,
        };

    private static HttpClient Http(ScriptedHandler handler) => new(handler);

    [Fact]
    public async Task Downloads_to_part_file()
    {
        using var tmp = new TempDir();
        var part = tmp.Combine("1.part");
        var handler = new ScriptedHandler()
            .Body(Encoding.UTF8.GetBytes("hello world"));
        var ctx = NewContext(new ImmediateTimeProvider());
        var taskId = ctx.Progress.AddTask("test");

        await new MirrorClient().FetchAsync(
            Http(handler), "https://catboy.best/d/1", part, taskId, ctx, ctx.Token);

        Assert.Equal("hello world", File.ReadAllText(part));
        Assert.Equal(11, ctx.Stats.Snapshot().Bytes);
        Assert.Equal("https://catboy.best/", handler.Requests[0].Headers["Referer"]);
    }

    [Fact]
    public async Task Resumes_with_range()
    {
        using var tmp = new TempDir();
        var part = tmp.Combine("1.part");
        File.WriteAllText(part, "abc");
        var handler = new ScriptedHandler()
            .Enqueue(_ => Responses.Range(206, 3, 5, 6, Encoding.UTF8.GetBytes("def")));
        var ctx = NewContext(new ImmediateTimeProvider());
        var taskId = ctx.Progress.AddTask("test");

        await new MirrorClient().FetchAsync(
            Http(handler), "https://catboy.best/d/1", part, taskId, ctx, ctx.Token);

        Assert.Equal("abcdef", File.ReadAllText(part));
        Assert.Equal("bytes=3-", handler.Requests[0].Headers["Range"]);
    }

    [Fact]
    public async Task Rate_limit_is_reported()
    {
        using var tmp = new TempDir();
        var handler = new ScriptedHandler().RateLimited(7);
        var ctx = NewContext(new ImmediateTimeProvider());
        var taskId = ctx.Progress.AddTask("test");

        var error = await Assert.ThrowsAsync<RateLimitedException>(() =>
            new MirrorClient().FetchAsync(
                Http(handler), "https://catboy.best/d/1", tmp.Combine("1.part"),
                taskId, ctx, ctx.Token));

        Assert.Equal(7, error.Seconds);
    }

    [Fact]
    public async Task Mirror_miss()
    {
        using var tmp = new TempDir();
        var handler = new ScriptedHandler().Missing();
        var ctx = NewContext(new ImmediateTimeProvider());
        var taskId = ctx.Progress.AddTask("test");

        await Assert.ThrowsAsync<MirrorMissException>(() =>
            new MirrorClient().FetchAsync(
                Http(handler), "https://catboy.best/d/1", tmp.Combine("1.part"),
                taskId, ctx, ctx.Token));
    }

    [Fact]
    public async Task Stop_aborts_transfer()
    {
        using var tmp = new TempDir();
        var part = tmp.Combine("1.part");
        var ctx = NewContext(new ImmediateTimeProvider());
        var taskId = ctx.Progress.AddTask("test");
        var handler = new ScriptedHandler().Enqueue(_ =>
        {
            ctx.Stop.Cancel();
            return Responses.Body(Encoding.UTF8.GetBytes("hello"));
        });

        await Assert.ThrowsAsync<StoppedException>(() =>
            new MirrorClient().FetchAsync(
                Http(handler), "https://catboy.best/d/1", part, taskId, ctx, ctx.Token));
    }

    [Fact]
    public async Task Bad_content_range_restarts()
    {
        using var tmp = new TempDir();
        var part = tmp.Combine("1.part");
        File.WriteAllText(part, "abc");
        var handler = new ScriptedHandler()
            .Enqueue(_ => Responses.Range(206, 0, 2, 6, Encoding.UTF8.GetBytes("def")));
        var ctx = NewContext(new ImmediateTimeProvider());
        var taskId = ctx.Progress.AddTask("test");

        await Assert.ThrowsAsync<HttpRequestException>(() =>
            new MirrorClient().FetchAsync(
                Http(handler), "https://catboy.best/d/1", part, taskId, ctx, ctx.Token));

        Assert.False(File.Exists(part));
    }
}

public class ChooseMirrorTests
{
    private static RunContext NewContext(out ManualTimeProvider time)
    {
        time = new ManualTimeProvider();
        return new RunContext(
            new CancellationTokenSource(), new RunLog(time), new TaskBoard(), time, new Random(1))
        {
            MinFreeGb = 0,
        };
    }

    [Fact]
    public void Returns_a_ready_mirror()
    {
        var ctx = NewContext(out _);
        var (mirror, wait) = new MirrorScheduler(ctx).Choose(new HashSet<string>());

        Assert.NotNull(mirror);
        Assert.Equal(TimeSpan.Zero, wait);
        Assert.Contains(MirrorTable.All, item => item.Name == mirror!.Name);
    }

    [Fact]
    public void All_cooling_returns_wait()
    {
        var ctx = NewContext(out var time);
        var until = time.GetUtcNow().AddSeconds(9_999_999_999);
        foreach (var item in MirrorTable.All)
        {
            ctx.Mirrors.State(item.Name).Park(until);
        }

        var (mirror, wait) = new MirrorScheduler(ctx).Choose(new HashSet<string>());

        Assert.Null(mirror);
        Assert.True(wait > TimeSpan.Zero);
    }

    [Fact]
    public void Tried_mirrors_are_skipped()
    {
        var ctx = NewContext(out _);
        var tried = MirrorTable.All.Select(mirror => mirror.Name).ToHashSet();

        var (mirror, wait) = new MirrorScheduler(ctx).Choose(tried);

        Assert.Null(mirror);
        Assert.Equal(TimeSpan.Zero, wait);
    }

    [Fact]
    public void Park_host_parks_every_endpoint_on_that_host()
    {
        var ctx = NewContext(out var time);
        var now = time.GetUtcNow();

        ctx.Mirrors.ParkHost("catboy.best", MirrorTable.All, 60, now, out _);

        Assert.True(ctx.Mirrors.State("catboy").Until > now);
        Assert.True(ctx.Mirrors.State("catboy-video").Until > now);
        Assert.Equal(default, ctx.Mirrors.State("nerinyan").Until);
    }
}

public class DownloadSetTests
{
    private static RunContext NewContext(TimeProvider time) =>
        new(new CancellationTokenSource(), new RunLog(time), new TaskBoard(), time, new Random(1))
        {
            MinFreeGb = 0,
        };

    private static AppConfig Config(string folder) =>
        ConfigValidator.Build(
            TestData.ApiRaw(folder, raw =>
            {
                raw.Workers = "1";
                raw.Batch = "1";
            }),
            new AppPaths(folder));

    [Fact]
    public async Task Successful_download()
    {
        using var tmp = new TempDir();
        var folder = tmp.Combine("out");
        Directory.CreateDirectory(folder);
        var cfg = Config(folder);
        var time = new ImmediateTimeProvider();
        var ctx = NewContext(time);
        var status = new StatusStore(folder, ctx.Log, time).Load();
        var handler = new ScriptedHandler().Body(TestData.MakeOsz());
        var service = new DownloadService(new HttpClient(handler), ctx);
        var overallId = ctx.Progress.AddTask("all", 1);
        var failed = new Dictionary<long, string>();

        await service.DownloadSetAsync(
            TestData.Set(123, title: "Test"), cfg, status, new SemaphoreSlim(1), overallId, failed);

        Assert.True(File.Exists(Path.Combine(folder, "123.osz")));
        Assert.Equal(new long[] { 123 }, status.Ids.OrderBy(id => id));
        Assert.Equal(1, ctx.Stats.Snapshot().Ok);
        Assert.Empty(failed);
        var overall = ctx.Progress.Snapshot().Tasks.Single(task => task.Description == "all");
        Assert.Equal(1, overall.Completed);
    }

    [Fact]
    public async Task All_mirrors_missing_marks_failure()
    {
        using var tmp = new TempDir();
        var folder = tmp.Combine("out");
        Directory.CreateDirectory(folder);
        var cfg = Config(folder);
        var time = new ImmediateTimeProvider();
        var ctx = NewContext(time);
        var status = new StatusStore(folder, ctx.Log, time).Load();
        var handler = new ScriptedHandler();
        for (var i = 0; i < MirrorTable.All.Count; i++)
        {
            handler.Missing();
        }

        var service = new DownloadService(new HttpClient(handler), ctx);
        var overallId = ctx.Progress.AddTask("all", 1);
        var failed = new Dictionary<long, string>();

        await service.DownloadSetAsync(
            TestData.Set(456, title: "Broken"), cfg, status,
            new SemaphoreSlim(1), overallId, failed);

        Assert.False(File.Exists(Path.Combine(folder, "456.osz")));
        Assert.Equal(new long[] { 456 }, status.Failed);
        Assert.Equal("Broken", failed[456]);
        Assert.Equal(1, ctx.Stats.Snapshot().Fail);
    }

    [Fact]
    public async Task Invalid_zip_is_rejected()
    {
        using var tmp = new TempDir();
        var folder = tmp.Combine("out");
        Directory.CreateDirectory(folder);
        var cfg = Config(folder);
        var time = new ImmediateTimeProvider();
        var ctx = NewContext(time);
        var status = new StatusStore(folder, ctx.Log, time).Load();
        var handler = new ScriptedHandler();
        var html = Encoding.UTF8.GetBytes("<html>nope</html>");
        for (var i = 0; i < MirrorTable.All.Count; i++)
        {
            handler.Body(html);
        }

        var service = new DownloadService(new HttpClient(handler), ctx);
        var overallId = ctx.Progress.AddTask("all", 1);
        var failed = new Dictionary<long, string>();

        await service.DownloadSetAsync(
            TestData.Set(789, title: "Bad"), cfg, status,
            new SemaphoreSlim(1), overallId, failed);

        Assert.False(File.Exists(Path.Combine(folder, "789.osz")));
        Assert.Equal("Bad", failed[789]);
    }
}
