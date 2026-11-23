using System.Text.Json;
using ManiaDL.Core.Logging;
using ManiaDL.Core.State;
using ManiaDL.Core.Tests.Support;
using Xunit;

namespace ManiaDL.Core.Tests;

// Ported from tests/test_state.py. Save batching is exercised through the real
// thresholds instead of patching module constants.
public class StatusMigrationTests
{
    private static StatusStore Load(string folder, out RunLog log, out ManualTimeProvider time)
    {
        time = new ManualTimeProvider();
        log = new RunLog(time);
        return new StatusStore(folder, log, time).Load();
    }

    [Fact]
    public void V1_is_upgraded_on_load()
    {
        using var tmp = new TempDir();
        TestData.WriteFile(tmp.Path, "status.json", """
            {"version": 1, "downloaded": {"11": "old"}, "failed": [22]}
            """);

        var status = Load(tmp.Path, out _, out _);

        using var payload = JsonDocument.Parse(File.ReadAllText(tmp.Combine("status.json")));
        Assert.Equal(2, payload.RootElement.GetProperty("version").GetInt32());
        Assert.Equal(new long[] { 11 }, status.Ids.OrderBy(id => id));
        Assert.Equal(new long[] { 22 }, status.Failed);
        Assert.Empty(payload.RootElement.GetProperty("titles").EnumerateObject());
    }

    [Fact]
    public void Legacy_text_files_are_imported()
    {
        using var tmp = new TempDir();
        TestData.WriteFile(tmp.Path, "downloaded_ids.txt", "33 44");
        TestData.WriteFile(tmp.Path, "failed.txt", "55");

        var status = Load(tmp.Path, out _, out _);

        Assert.Equal(new long[] { 33, 44 }, status.Ids.OrderBy(id => id));
        Assert.Equal(new long[] { 55 }, status.Failed);
        Assert.True(File.Exists(tmp.Combine("status.json")));
        Assert.False(File.Exists(tmp.Combine("downloaded_ids.txt")));
        Assert.False(File.Exists(tmp.Combine("failed.txt")));
    }

    [Fact]
    public void Stale_legacy_files_are_removed_when_status_exists()
    {
        using var tmp = new TempDir();
        TestData.WriteFile(tmp.Path, "status.json", """
            {"version": 2, "downloaded": {"11": "old"}, "failed": [], "titles": {}}
            """);
        TestData.WriteFile(tmp.Path, "downloaded_ids.txt", "33");
        TestData.WriteFile(tmp.Path, "failed.txt", "55");

        var status = Load(tmp.Path, out _, out _);

        Assert.Equal(new long[] { 11 }, status.Ids.OrderBy(id => id));
        Assert.False(File.Exists(tmp.Combine("downloaded_ids.txt")));
        Assert.False(File.Exists(tmp.Combine("failed.txt")));
    }

    [Fact]
    public void Invalid_json_is_rebuilt()
    {
        using var tmp = new TempDir();
        TestData.WriteFile(tmp.Path, "status.json", "{nope");

        var status = Load(tmp.Path, out var log, out _);

        Assert.Empty(status.Ids);
        Assert.Empty(status.Failed);
        Assert.Contains(log.Recent(), entry => entry.Message.Contains("isn't valid JSON"));
    }
}

public class StatusBehaviourTests
{
    private static StatusStore Load(string folder, out ManualTimeProvider time)
    {
        time = new ManualTimeProvider();
        return new StatusStore(folder, new RunLog(time), time).Load();
    }

    private static JsonElement ReadPayload(string folder)
    {
        return JsonDocument.Parse(File.ReadAllText(Path.Combine(folder, "status.json"))).RootElement;
    }

    [Fact]
    public void Success_removes_failure_and_title()
    {
        using var tmp = new TempDir();
        var status = Load(tmp.Path, out _);

        status.NoteFailure(1, "Broken");
        status.NoteSuccess(1);
        status.Flush();

        var payload = ReadPayload(tmp.Path);
        Assert.Empty(payload.GetProperty("failed").EnumerateArray());
        Assert.Empty(payload.GetProperty("titles").EnumerateObject());
        Assert.NotEqual("", payload.GetProperty("downloaded").GetProperty("1").GetString());
    }

    [Fact]
    public void Prune_failed_drops_present_ids()
    {
        using var tmp = new TempDir();
        var status = Load(tmp.Path, out _);

        status.NoteFailure(1, "One");
        status.NoteFailure(2, "Two");
        status.PruneFailed(new HashSet<long> { 2 });

        Assert.Equal(new long[] { 1 }, status.Failed);
        Assert.Equal("One", status.Titles[1]);
    }

    [Fact]
    public void Batched_saves()
    {
        using var tmp = new TempDir();
        var status = Load(tmp.Path, out _);

        // The first note always saves (the save interval counts from process start).
        status.NoteSuccess(1);
        Assert.True(File.Exists(tmp.Combine("status.json")));
        Assert.Single(ReadPayload(tmp.Path).GetProperty("downloaded").EnumerateObject());

        // Seven more notes stay in memory: SAVE_EVERY is 8.
        for (var id = 2; id <= 8; id++)
        {
            status.NoteSuccess(id);
        }

        Assert.Single(ReadPayload(tmp.Path).GetProperty("downloaded").EnumerateObject());

        // The eighth dirty note flushes.
        status.NoteSuccess(9);
        Assert.Equal(9, ReadPayload(tmp.Path).GetProperty("downloaded").EnumerateObject().Count());
        Assert.False(File.Exists(tmp.Combine("status.json.tmp")));
    }

    [Fact]
    public void Scan_existing()
    {
        using var tmp = new TempDir();
        File.WriteAllBytes(tmp.Combine("123.osz"), new byte[] { 1 });
        File.WriteAllBytes(tmp.Combine("456 Title.osz"), new byte[] { 1 });
        File.WriteAllBytes(tmp.Combine("789.part"), new byte[] { 1 });
        File.WriteAllBytes(tmp.Combine("notanid.osz"), new byte[] { 1 });

        Assert.Equal(new long[] { 123, 456 }, FolderScanner.ScanExisting(tmp.Path).OrderBy(id => id));
    }
}
