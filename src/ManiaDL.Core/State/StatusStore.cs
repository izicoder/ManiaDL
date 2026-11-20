using System.Globalization;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;
using ManiaDL.Core.Constants;
using ManiaDL.Core.Logging;
using ManiaDL.Core.Util;

namespace ManiaDL.Core.State;

/// <summary>
/// Atomic, batched status.json owner. Shape (version 2):
/// <code>
/// {
///   "version": 2,
///   "updated": "...",
///   "downloaded": {"123": "stamp"},
///   "failed": [456],
///   "titles": {"456": "Set title"}
/// }
/// </code>
/// Version 1 files are read as-is and upgraded on first save.
/// </summary>
public sealed class StatusStore
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        Converters = { new JsonStringEnumConverter() },
    };

    private readonly object _lock = new();
    private readonly string _folder;
    private readonly string _path;
    private readonly RunLog _log;
    private readonly TimeProvider _time;

    private readonly SortedDictionary<long, string> _downloaded = new();
    private readonly List<long> _failed = new();
    private readonly SortedDictionary<long, string> _titles = new();

    private int _version = Limits.StatusVersion;
    private string _updated = "";
    private int _dirty;
    private bool _hasSaved;
    private long _lastSaveTimestamp;

    public StatusStore(string folder, RunLog log, TimeProvider time)
    {
        _folder = folder;
        _path = PathUtil.StatusPath(folder);
        _log = log;
        _time = time;
    }

    public string Path => _path;

    public StatusStore Load()
    {
        JsonDocument? document = null;
        try
        {
            var text = File.ReadAllText(_path);
            document = JsonDocument.Parse(text);
        }
        catch (Exception ex) when (ex is FileNotFoundException or DirectoryNotFoundException)
        {
            document = null;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            document = null;
        }
        catch (JsonException)
        {
            _log.Warning($"{Limits.StatusFileName} isn't valid JSON; rebuilding it.");
            document = null;
        }

        using (document)
        {
            if (document is { RootElement.ValueKind: JsonValueKind.Object })
            {
                var root = document.RootElement;
                _version = ReadVersion(root);

                if (root.TryGetProperty("downloaded", out var downloaded))
                {
                    ReadDownloaded(downloaded);
                }

                if (root.TryGetProperty("failed", out var failed) &&
                    failed.ValueKind == JsonValueKind.Array)
                {
                    foreach (var item in failed.EnumerateArray())
                    {
                        if (TryReadLong(item, out var id))
                        {
                            _failed.Add(id);
                        }
                    }

                    _failed.Sort();
                }

                if (root.TryGetProperty("titles", out var titles) &&
                    titles.ValueKind == JsonValueKind.Object)
                {
                    foreach (var property in titles.EnumerateObject())
                    {
                        if (long.TryParse(property.Name, NumberStyles.Integer, CultureInfo.InvariantCulture, out var id) &&
                            property.Value.ValueKind == JsonValueKind.String &&
                            !string.IsNullOrWhiteSpace(property.Value.GetString()))
                        {
                            _titles[id] = property.Value.GetString()!;
                        }
                    }
                }

                if (root.TryGetProperty("updated", out var updated) &&
                    updated.ValueKind == JsonValueKind.String)
                {
                    _updated = updated.GetString() ?? "";
                }
            }
        }

        MigrateLegacy();

        // First run of this version: rewrite v1 in place as v2.
        if (File.Exists(_path) && _version < Limits.StatusVersion)
        {
            Save();
        }

        return this;
    }

    private void ReadDownloaded(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            foreach (var property in element.EnumerateObject())
            {
                if (long.TryParse(property.Name, NumberStyles.Integer, CultureInfo.InvariantCulture, out var id))
                {
                    _downloaded[id] = property.Value.ValueKind == JsonValueKind.String
                        ? property.Value.GetString() ?? ""
                        : property.Value.ToString();
                }
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in element.EnumerateArray())
            {
                if (TryReadLong(item, out var id))
                {
                    _downloaded[id] = "";
                }
            }
        }
    }

    private static int ReadVersion(JsonElement root)
    {
        if (!root.TryGetProperty("version", out var version))
        {
            return 1;
        }

        return TryReadLong(version, out var number) ? (int)number : 1;
    }

    private static bool TryReadLong(JsonElement element, out long value)
    {
        value = 0;
        return element.ValueKind switch
        {
            JsonValueKind.Number => element.TryGetInt64(out value),
            JsonValueKind.String => long.TryParse(
                element.GetString(), NumberStyles.Integer, CultureInfo.InvariantCulture, out value),
            _ => false,
        };
    }

    private void MigrateLegacy()
    {
        if (File.Exists(_path))
        {
            // status.json is authoritative; old text files are redundant.
            foreach (var name in new[] { Limits.LegacyIdsFileName, Limits.LegacyFailedFileName })
            {
                TryDelete(System.IO.Path.Combine(_folder, name));
            }

            return;
        }

        var moved = new List<string>();

        var oldIds = System.IO.Path.Combine(_folder, Limits.LegacyIdsFileName);
        var stamp = "";
        try
        {
            stamp = Stamp(File.GetLastWriteTimeUtc(oldIds));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            stamp = "";
        }

        try
        {
            foreach (var token in File.ReadAllText(oldIds).Split(
                         (char[]?)null, StringSplitOptions.RemoveEmptyEntries))
            {
                if (long.TryParse(token, NumberStyles.Integer, CultureInfo.InvariantCulture, out var id) &&
                    !_downloaded.ContainsKey(id))
                {
                    _downloaded[id] = stamp;
                }
            }

            moved.Add(Limits.LegacyIdsFileName);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // Missing legacy file is the normal case.
        }

        var oldFailed = System.IO.Path.Combine(_folder, Limits.LegacyFailedFileName);
        try
        {
            foreach (var token in File.ReadAllText(oldFailed).Split(
                         (char[]?)null, StringSplitOptions.RemoveEmptyEntries))
            {
                if (long.TryParse(token, NumberStyles.Integer, CultureInfo.InvariantCulture, out var id) &&
                    !_failed.Contains(id))
                {
                    _failed.Add(id);
                }
            }

            _failed.Sort();
            moved.Add(Limits.LegacyFailedFileName);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // Missing legacy file is the normal case.
        }

        if (moved.Count > 0 && Save())
        {
            // Keep the download folder to osz files + status.json only.
            foreach (var name in moved)
            {
                TryDelete(System.IO.Path.Combine(_folder, name));
            }

            _log.Info($"Imported {string.Join(" and ", moved)} into {Limits.StatusFileName} " +
                      "and removed the old text files.");
        }
    }

    public HashSet<long> Ids
    {
        get
        {
            lock (_lock)
            {
                return _downloaded.Keys.ToHashSet();
            }
        }
    }

    public IReadOnlyList<long> Failed
    {
        get
        {
            lock (_lock)
            {
                return _failed.ToArray();
            }
        }
    }

    public IReadOnlyDictionary<long, string> Titles
    {
        get
        {
            lock (_lock)
            {
                return _titles.ToDictionary(pair => pair.Key, pair => pair.Value);
            }
        }
    }

    public void NoteSuccess(long id)
    {
        lock (_lock)
        {
            _downloaded[id] = Stamp(_time.GetLocalNow());
            _failed.RemoveAll(item => item == id);
            _titles.Remove(id);
        }

        MaybeSave();
    }

    public void NoteFailure(long id, string title = "")
    {
        lock (_lock)
        {
            if (!_failed.Contains(id))
            {
                _failed.Add(id);
                _failed.Sort();
            }

            if (!string.IsNullOrEmpty(title))
            {
                _titles[id] = title;
            }
        }

        MaybeSave();
    }

    /// <summary>Drop failed entries that are already on disk (e.g. manual download).</summary>
    public void PruneFailed(IReadOnlySet<long> presentIds)
    {
        bool had;
        lock (_lock)
        {
            had = _failed.Any(presentIds.Contains);
            if (!had)
            {
                return;
            }

            _failed.RemoveAll(presentIds.Contains);
            foreach (var id in _failed.ToArray())
            {
                if (presentIds.Contains(id))
                {
                    _titles.Remove(id);
                }
            }

            // Remove titles for anything that is no longer failed.
            var failed = _failed.ToHashSet();
            foreach (var id in _titles.Keys.ToArray())
            {
                if (!failed.Contains(id))
                {
                    _titles.Remove(id);
                }
            }
        }

        Save();
    }

    public void Flush() => Save();

    private void MaybeSave()
    {
        bool save;
        lock (_lock)
        {
            _dirty++;
            save = _dirty >= Limits.SaveEvery || !_hasSaved ||
                   _time.GetElapsedTime(_lastSaveTimestamp, _time.GetTimestamp()) >=
                   TimeSpan.FromSeconds(Limits.SaveIntervalSeconds);
        }

        if (save)
        {
            Save();
        }
    }

    public bool Save()
    {
        string json;
        string updated;
        lock (_lock)
        {
            updated = Stamp(_time.GetLocalNow());
            _updated = updated;

            var failedSet = _failed.ToHashSet();
            var titles = new SortedDictionary<long, string>();
            foreach (var pair in _titles)
            {
                if (failedSet.Contains(pair.Key))
                {
                    titles[pair.Key] = pair.Value;
                }
            }

            var payload = new StatusPayload(
                Limits.StatusVersion,
                updated,
                new SortedDictionary<long, string>(_downloaded),
                _failed.ToArray(),
                titles);
            json = JsonSerializer.Serialize(payload, JsonOptions);
        }

        try
        {
            AtomicFile.WriteText(_path, json);
            lock (_lock)
            {
                _dirty = 0;
                _hasSaved = true;
                _lastSaveTimestamp = _time.GetTimestamp();
                _version = Limits.StatusVersion;
                _updated = updated;
            }

            return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _log.Warning($"Couldn't write {Limits.StatusFileName}: {ex.Message}");
            return false;
        }
    }

    private void TryDelete(string path)
    {
        try
        {
            File.Delete(path);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // Best effort only.
        }
    }

    private static string Stamp(DateTimeOffset value) =>
        value.ToLocalTime().ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture);

    private static string Stamp(DateTime utc)
    {
        var local = utc.Kind == DateTimeKind.Utc ? utc.ToLocalTime() : utc;
        return local.ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture);
    }

    private sealed record StatusPayload(
        [property: JsonPropertyName("version"), JsonPropertyOrder(0)] int Version,
        [property: JsonPropertyName("updated"), JsonPropertyOrder(1)] string Updated,
        [property: JsonPropertyName("downloaded"), JsonPropertyOrder(2)] SortedDictionary<long, string> Downloaded,
        [property: JsonPropertyName("failed"), JsonPropertyOrder(3)] long[] Failed,
        [property: JsonPropertyName("titles"), JsonPropertyOrder(4)] SortedDictionary<long, string> Titles);
}
