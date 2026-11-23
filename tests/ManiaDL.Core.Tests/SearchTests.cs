using System.Text.Json;
using ManiaDL.Core.Api;
using ManiaDL.Core.Config;
using ManiaDL.Core.Logging;
using ManiaDL.Core.Tests.Support;
using ManiaDL.Core.Util;
using Xunit;

namespace ManiaDL.Core.Tests;

// Ported from tests/test_api.py (search half).
public class SearchTests
{
    private static OsuApiClient Client(ManualTimeProvider time, ScriptedHandler handler) =>
        new(new HttpClient(handler), time, new RunLog(time), new Random(42));

    private static string Page(IEnumerable<Beatmapset> sets, string? cursor) =>
        JsonSerializer.Serialize(new Dictionary<string, object?>
        {
            ["beatmapsets"] = sets.ToList(),
            ["cursor_string"] = cursor,
        });

    [Fact]
    public async Task Paginates_and_filters()
    {
        using var tmp = new TempDir();
        var cfg = ConfigValidator.Build(
            TestData.ApiRaw(tmp.Combine("out"), raw =>
            {
                raw.Keys = "4";
                raw.MinSr = "4";
                raw.MaxSr = "7";
            }),
            new AppPaths(tmp.Path));

        var handler = new ScriptedHandler()
            .Json(Page(new[] { TestData.Set(1), TestData.Set(2, status: "loved") }, "cursor-1"))
            .Json(Page(new[] { TestData.Set(3) }, null));
        var time = new ManualTimeProvider();
        var messages = new List<string>();

        var sets = await TestClock.AdvanceUntilAsync(
            time,
            Client(time, handler).SearchSetsAsync("token", cfg, messages.Add, CancellationToken.None));

        Assert.Equal(new long[] { 1, 3 }, sets.Select(set => set.Id));
        Assert.Equal(2, handler.Requests.Count);
        Assert.Equal("cursor-1", handler.Requests[1].Query("cursor_string"));
        Assert.NotEmpty(messages);
    }

    [Fact]
    public async Task Http_400_falls_back_to_the_minimal_query()
    {
        using var tmp = new TempDir();
        var cfg = ConfigValidator.Build(
            TestData.AdvancedRaw(tmp.Combine("out")), new AppPaths(tmp.Path));

        var handler = new ScriptedHandler()
            .Status(400, "bad query")
            .Json(Page(new[] { TestData.Set(1) }, null));
        var time = new ManualTimeProvider();

        var sets = await TestClock.AdvanceUntilAsync(
            time,
            Client(time, handler).SearchSetsAsync("token", cfg, null, CancellationToken.None));

        Assert.Equal(new long[] { 1 }, sets.Select(set => set.Id));
        Assert.Equal(2, handler.Requests.Count);
        Assert.Contains("camellia", handler.Requests[1].Query("q"));
    }

    [Fact]
    public async Task Http_400_raises_search_rejected()
    {
        using var tmp = new TempDir();
        var cfg = TestData.Cfg(tmp.Combine("out"));

        var handler = new ScriptedHandler()
            .Status(400, "bad query")
            .Status(400, "bad query")
            .Status(400, "bad query");
        var time = new ManualTimeProvider();

        await Assert.ThrowsAsync<SearchRejectedException>(() =>
            TestClock.AdvanceUntilAsync(
                time,
                Client(time, handler).SearchSetsAsync("token", cfg, null, CancellationToken.None)));

        Assert.Equal(3, handler.Requests.Count);
    }

    [Fact]
    public async Task Http_429_waits_and_retries()
    {
        using var tmp = new TempDir();
        var cfg = TestData.Cfg(tmp.Combine("out"));

        var handler = new ScriptedHandler()
            .RateLimited(1)
            .Json(Page(Array.Empty<Beatmapset>(), null));
        var time = new ManualTimeProvider();

        var sets = await TestClock.AdvanceUntilAsync(
            time,
            Client(time, handler).SearchSetsAsync("token", cfg, null, CancellationToken.None));

        Assert.Empty(sets);
        Assert.Equal(2, handler.Requests.Count);
    }

    [Fact]
    public async Task Genre_and_language_are_sent_as_api_params()
    {
        using var tmp = new TempDir();
        var cfg = TestData.AdvancedCfg(tmp.Combine("out"));

        var handler = new ScriptedHandler().Json(Page(Array.Empty<Beatmapset>(), null));
        var time = new ManualTimeProvider();

        await TestClock.AdvanceUntilAsync(
            time,
            Client(time, handler).SearchSetsAsync("token", cfg, null, CancellationToken.None));

        var parameters = handler.Requests[0];
        Assert.Equal("10", parameters.Query("g"));
        Assert.Equal("5", parameters.Query("l"));
    }
}

// Ported from tests/test_api.py (SearchPacerTests).
public class SearchPacerTests
{
    [Fact]
    public async Task Second_request_waits_for_the_interval()
    {
        var time = new ManualTimeProvider();
        var pacer = new SearchPacer(time, new Random(1), interval: 5.0);

        await pacer.WaitAsync(CancellationToken.None);
        var second = pacer.WaitAsync(CancellationToken.None);
        await Task.Delay(50);
        Assert.False(second.IsCompleted);

        time.Advance(TimeSpan.FromSeconds(6));
        await second;
        Assert.Equal(2, pacer.Requests);
    }

    [Fact]
    public void Rate_limit_stretches_then_recovers()
    {
        var pacer = new SearchPacer(new ManualTimeProvider(), new Random(1), interval: 1.0);
        pacer.Penalise(12);
        Assert.Equal(12.0, pacer.Interval);

        for (var i = 0; i < 40; i++)
        {
            pacer.Success();
        }

        Assert.Equal(1.0, pacer.Interval);
    }
}
