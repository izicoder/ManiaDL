using System.Text.Json;
using ManiaDL.Core.Api;
using ManiaDL.Core.Config;
using ManiaDL.Core.Constants;
using ManiaDL.Core.Logging;
using ManiaDL.Core.Progress;
using ManiaDL.Core.Run;
using ManiaDL.Core.Tests.Support;
using ManiaDL.Core.Util;
using Xunit;

namespace ManiaDL.Core.Tests;

// Ported 1:1 from tests/test_app.py (fake HTTP, no network).
public class OrchestratorTests
{
    private static RunContext NewContext(out ImmediateTimeProvider time)
    {
        time = new ImmediateTimeProvider();
        return new RunContext(
            new CancellationTokenSource(), new RunLog(time), new TaskBoard(), time, new Random(1))
        {
            MinFreeGb = 0,
        };
    }

    private static AppConfig Config(string folder) =>
        ConfigValidator.Build(
            TestData.ApiRaw(folder, raw =>
            {
                raw.Keys = "4";
                raw.Limit = "10";
                raw.Workers = "1";
                raw.Batch = "5";
            }),
            new AppPaths(folder));

    private static string Page(IEnumerable<Beatmapset> sets) =>
        JsonSerializer.Serialize(new Dictionary<string, object?>
        {
            ["beatmapsets"] = sets.ToList(),
            ["cursor_string"] = null,
        });

    private static string Token() => """{"access_token": "token"}""";

    private static ScriptedHandler SuccessHandler(params Beatmapset[] sets)
    {
        var handler = new ScriptedHandler().Json(Token()).Json(Page(sets));
        handler.Body(TestData.MakeOsz());
        return handler;
    }

    private static async Task<(RunResult Result, ScriptedHandler Handler)> RunAsync(
        string folder, ScriptedHandler handler)
    {
        var ctx = NewContext(out _);
        var orchestrator = new DownloadOrchestrator(ctx, () => handler);
        var result = await orchestrator.RunAsync(Config(folder), "1234", "secret");
        return (result, handler);
    }

    [Fact]
    public async Task Full_run_downloads_and_records_status()
    {
        using var tmp = new TempDir();
        var folder = tmp.Combine("out");
        var handler = SuccessHandler(TestData.Set(123, title: "Test Set"));

        var (result, requests) = await RunAsync(folder, handler);

        Assert.True(File.Exists(Path.Combine(folder, "123.osz")));
        using var payload = JsonDocument.Parse(File.ReadAllText(Path.Combine(folder, "status.json")));
        Assert.Equal(
            new[] { "123" },
            payload.RootElement.GetProperty("downloaded").EnumerateObject().Select(p => p.Name));
        Assert.Empty(payload.RootElement.GetProperty("failed").EnumerateArray());
        Assert.False(File.Exists(Path.Combine(folder, "failed_links.txt")));

        Assert.Equal(1, result.Matched);
        Assert.Equal(1, result.Todo);
        Assert.Empty(result.NewFailed);

        Assert.Contains(requests.Requests, request =>
            request.Method == "GET" &&
            request.Uri.ToString().StartsWith("https://osu.ppy.sh/api/v2/beatmapsets/search"));
        Assert.Equal("https://osu.ppy.sh/oauth/token", requests.Requests[0].Uri.ToString());
        Assert.Equal("POST", requests.Requests[0].Method);
    }

    [Fact]
    public async Task All_mirrors_failing_keeps_links_in_memory()
    {
        using var tmp = new TempDir();
        var folder = tmp.Combine("out");
        var handler = new ScriptedHandler()
            .Json(Token())
            .Json(Page(new[] { TestData.Set(456, title: "Broken") }));
        for (var i = 0; i < MirrorTable.All.Count; i++)
        {
            handler.Missing();
        }

        var (result, _) = await RunAsync(folder, handler);

        Assert.False(File.Exists(Path.Combine(folder, "456.osz")));
        using var payload = JsonDocument.Parse(File.ReadAllText(Path.Combine(folder, "status.json")));
        Assert.Equal(
            new long[] { 456 },
            payload.RootElement.GetProperty("failed").EnumerateArray().Select(item => item.GetInt64()));
        Assert.Equal(
            "Broken",
            payload.RootElement.GetProperty("titles").GetProperty("456").GetString());
        Assert.False(File.Exists(Path.Combine(folder, "failed_links.txt")));
        Assert.Equal("Broken", result.NewFailed[456]);
    }

    [Fact]
    public async Task Stale_link_report_is_removed()
    {
        using var tmp = new TempDir();
        var folder = tmp.Combine("out");
        Directory.CreateDirectory(folder);
        File.WriteAllText(Path.Combine(folder, "failed_links.txt"), "old");
        var handler = SuccessHandler(TestData.Set(123, title: "Test Set"));

        await RunAsync(folder, handler);

        Assert.False(File.Exists(Path.Combine(folder, "failed_links.txt")));
    }

    [Fact]
    public async Task Log_events_are_emitted()
    {
        using var tmp = new TempDir();
        var folder = tmp.Combine("out");
        var time = new ImmediateTimeProvider();
        var ctx = new RunContext(
            new CancellationTokenSource(), new RunLog(time), new TaskBoard(), time, new Random(1))
        {
            MinFreeGb = 0,
        };
        var handler = SuccessHandler(TestData.Set(123, title: "Test Set"));
        var orchestrator = new DownloadOrchestrator(ctx, () => handler);

        await orchestrator.RunAsync(Config(folder), "1234", "secret");

        var lines = new List<string>();
        while (ctx.Log.Reader.TryRead(out var entry))
        {
            lines.Add(entry.Message);
        }

        var joined = string.Join("\n", lines);
        Assert.Contains("Search finished", joined);
        Assert.Contains("123 via", joined);
    }
}
