using System.Text;
using System.Text.Json;
using ManiaDL.Core.Api;
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

/// <summary>
/// Extra tests the Python suite lacked: golden files, cross-run folder contract,
/// concurrency and host pacing.
/// </summary>
public class GoldenFileTests
{
    private static string Fixture(string name) =>
        Path.Combine(AppContext.BaseDirectory, "Fixtures", name);

    [Fact]
    public void Python_status_v2_is_read_and_round_trips()
    {
        using var tmp = new TempDir();
        File.Copy(Fixture("status-v2.json"), tmp.Combine("status.json"));
        var time = new ManualTimeProvider();
        var status = new StatusStore(tmp.Path, new RunLog(time), time).Load();

        Assert.Equal(new long[] { 11, 22 }, status.Ids.OrderBy(id => id));
        Assert.Equal(new long[] { 33, 44 }, status.Failed);
        Assert.Equal("Broken [map]", status.Titles[33]);
        Assert.Equal("Other", status.Titles[44]);

        status.Flush();
        var bytes = File.ReadAllBytes(tmp.Combine("status.json"));
        Assert.False(bytes.Length >= 3 && bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF,
            "status.json must be UTF-8 without BOM");

        using var document = JsonDocument.Parse(bytes);
        Assert.Equal(
            new[] { "version", "updated", "downloaded", "failed", "titles" },
            document.RootElement.EnumerateObject().Select(property => property.Name));
        Assert.Equal(2, document.RootElement.GetProperty("version").GetInt32());
        Assert.Equal(
            new long[] { 33, 44 },
            document.RootElement.GetProperty("failed").EnumerateArray().Select(item => item.GetInt64()));
        Assert.Equal(
            "Broken [map]",
            document.RootElement.GetProperty("titles").GetProperty("33").GetString());
        Assert.Equal(
            "",
            document.RootElement.GetProperty("downloaded").GetProperty("22").GetString());
        Assert.False(File.Exists(tmp.Combine("status.json.tmp")));
    }

    [Fact]
    public void Python_status_v1_is_upgraded_from_the_golden_file()
    {
        using var tmp = new TempDir();
        File.Copy(Fixture("status-v1.json"), tmp.Combine("status.json"));
        var time = new ManualTimeProvider();
        var status = new StatusStore(tmp.Path, new RunLog(time), time).Load();

        Assert.Equal(new long[] { 11 }, status.Ids.OrderBy(id => id));
        Assert.Equal(new long[] { 22 }, status.Failed);

        using var document = JsonDocument.Parse(File.ReadAllText(tmp.Combine("status.json")));
        Assert.Equal(2, document.RootElement.GetProperty("version").GetInt32());
        Assert.Empty(document.RootElement.GetProperty("titles").EnumerateObject());
    }

    [Fact]
    public void Python_config_is_migrated_without_losing_values()
    {
        using var tmp = new TempDir();
        File.Copy(Fixture("mania_dl_config.json"), tmp.Combine("mania_dl_config.json"));
        var store = new ConfigStore(new AppPaths(tmp.Path));

        var (config, changed) = store.LoadAndMigrate();

        Assert.True(changed);
        Assert.Equal("1234", config.ClientId);
        Assert.Equal("ranked,loved", config.Statuses);
        Assert.Equal("4", config.Workers);
        Assert.Equal(@"C:\mania", config.Out);
        Assert.False(config.Extra?.ContainsKey("safe_mode") ?? false);

        Assert.True(store.Save(config));
        using var document = JsonDocument.Parse(File.ReadAllText(store.Path));
        var root = document.RootElement;
        Assert.Equal(@"C:\mania", root.GetProperty("out").GetString());
        Assert.Equal("ranked,loved", root.GetProperty("statuses").GetString());
        Assert.True(root.TryGetProperty("bpm_range", out _));
        Assert.False(root.TryGetProperty("safe_mode", out _));
    }
}

public class FolderContractTests
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

    private static AppConfig Config(string folder, Action<RawConfig>? edit = null) =>
        ConfigValidator.Build(
            TestData.ApiRaw(folder, raw =>
            {
                raw.Keys = "4";
                raw.Workers = "1";
                raw.Batch = "1";
                edit?.Invoke(raw);
            }),
            new AppPaths(folder));

    private static string Page(IEnumerable<Beatmapset> sets) =>
        JsonSerializer.Serialize(new Dictionary<string, object?>
        {
            ["beatmapsets"] = sets.ToList(),
            ["cursor_string"] = null,
        });

    [Fact]
    public async Task Valid_osz_already_on_disk_is_recorded_but_not_counted()
    {
        using var tmp = new TempDir();
        var folder = tmp.Combine("out");
        Directory.CreateDirectory(folder);
        TestData.WriteOsz(folder, "999.osz");

        var time = new ImmediateTimeProvider();
        var ctx = NewContext(out _);
        var status = new StatusStore(folder, ctx.Log, time).Load();
        var handler = new ScriptedHandler();
        var service = new DownloadService(new HttpClient(handler), ctx);
        var overallId = ctx.Progress.AddTask("all", 1);
        var failed = new Dictionary<long, string>();

        await service.DownloadSetAsync(
            TestData.Set(999, title: "On disk"), Config(folder), status,
            new SemaphoreSlim(1), overallId, failed);

        Assert.Empty(handler.Requests);
        Assert.Equal(0, ctx.Stats.Snapshot().Ok);
        Assert.Equal(new long[] { 999 }, status.Ids.OrderBy(id => id));
        Assert.Empty(failed);
    }

    [Fact]
    public async Task Status_ids_skip_sets_even_when_the_osz_was_removed()
    {
        using var tmp = new TempDir();
        var folder = tmp.Combine("out");
        Directory.CreateDirectory(folder);
        TestData.WriteFile(folder, "status.json", """
            {"version": 2, "updated": "", "downloaded": {"555": ""}, "failed": [], "titles": {}}
            """);

        var handler = new ScriptedHandler()
            .Json("""{"access_token": "token"}""")
            .Json(Page(new[] { TestData.Set(555, title: "Gone") }));
        var ctx = NewContext(out _);
        var orchestrator = new DownloadOrchestrator(ctx, () => handler);

        var result = await orchestrator.RunAsync(Config(folder), "1234", "secret");

        Assert.Equal(1, result.Matched);
        Assert.Equal(0, result.Todo);
        Assert.False(File.Exists(Path.Combine(folder, "555.osz")));
        Assert.Equal(2, handler.Requests.Count);
    }

    [Fact]
    public async Task Part_leftovers_are_cleaned_at_run_end()
    {
        using var tmp = new TempDir();
        var folder = tmp.Combine("out");
        Directory.CreateDirectory(folder);
        File.WriteAllText(Path.Combine(folder, "1.part"), "leftover");

        var handler = new ScriptedHandler()
            .Json("""{"access_token": "token"}""")
            .Json(Page(new[] { TestData.Set(123, title: "Test Set") }))
            .Body(TestData.MakeOsz());
        var ctx = NewContext(out _);
        var orchestrator = new DownloadOrchestrator(ctx, () => handler);

        await orchestrator.RunAsync(Config(folder), "1234", "secret");

        Assert.Empty(Directory.GetFiles(folder, "*.part"));
        Assert.True(File.Exists(Path.Combine(folder, "123.osz")));
        Assert.True(File.Exists(Path.Combine(folder, "status.json")));
        Assert.Equal(
            new[] { "123.osz", "status.json" },
            Directory.GetFiles(folder).Select(Path.GetFileName).OrderBy(name => name));
    }

    [Fact]
    public async Task Stop_mid_run_leaves_queued_sets_absent_from_status()
    {
        using var tmp = new TempDir();
        var folder = tmp.Combine("out");
        var ctx = NewContext(out _);
        var handler = new ScriptedHandler()
            .Json("""{"access_token": "token"}""")
            .Json(Page(new[] { TestData.Set(1, title: "One"), TestData.Set(2, title: "Two") }))
            .Body(TestData.MakeOsz())
            .Enqueue(_ =>
            {
                ctx.Stop.Cancel();
                return Responses.Body(TestData.MakeOsz());
            });
        var orchestrator = new DownloadOrchestrator(ctx, () => handler);

        var result = await orchestrator.RunAsync(Config(folder), "1234", "secret");

        using var payload = JsonDocument.Parse(File.ReadAllText(Path.Combine(folder, "status.json")));
        Assert.Equal(
            new[] { "1" },
            payload.RootElement.GetProperty("downloaded").EnumerateObject().Select(p => p.Name));
        Assert.Empty(payload.RootElement.GetProperty("failed").EnumerateArray());
        Assert.False(File.Exists(Path.Combine(folder, "2.osz")));
        Assert.True(result.Stopped);
    }
}

public class ConcurrencyTests
{
    [Fact]
    public async Task Stats_and_mirror_choice_are_exact_under_parallelism()
    {
        var time = new ImmediateTimeProvider();
        var ctx = new RunContext(
            new CancellationTokenSource(), new RunLog(time), new TaskBoard(), time, Random.Shared)
        {
            MinFreeGb = 0,
        };

        var tasks = Enumerable.Range(0, 200).Select(index => Task.Run(() =>
        {
            ctx.Stats.AddBytes(index);
            if (index % 2 == 0)
            {
                ctx.Stats.AddOk();
            }
            else
            {
                ctx.Stats.AddFail();
            }

            var scheduler = new MirrorScheduler(ctx);
            var chosen = scheduler.Choose(new HashSet<string>());
            Assert.NotNull(chosen.Mirror);
        }));

        await Task.WhenAll(tasks);

        var snapshot = ctx.Stats.Snapshot();
        Assert.Equal(100, snapshot.Ok);
        Assert.Equal(100, snapshot.Fail);
        Assert.Equal(Enumerable.Range(0, 200).Sum(index => (long)index), snapshot.Bytes);
    }

    [Fact]
    public async Task Host_starts_are_spaced_from_the_request_start()
    {
        var time = new ManualTimeProvider();
        var gate = new HostGate(time, new Random(1));

        using (await gate.AcquireAsync(CancellationToken.None))
        {
            // First request starts immediately.
        }

        var second = gate.AcquireAsync(CancellationToken.None);
        await Task.Delay(30);
        Assert.False(second.IsCompleted);

        // 0.9 s * U(0.85, 1.15) means at least 0.765 s between starts.
        time.Advance(TimeSpan.FromSeconds(0.7));
        await Task.Delay(30);
        Assert.False(second.IsCompleted);

        time.Advance(TimeSpan.FromSeconds(0.5));
        using var slot = await second;
        Assert.Equal(1, gate.Inflight);
    }
}
