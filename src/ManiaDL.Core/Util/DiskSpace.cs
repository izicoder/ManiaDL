using ManiaDL.Core.Constants;

namespace ManiaDL.Core.Util;

/// <summary>Cached disk-free lookup so the live dashboard does not stat constantly.</summary>
public sealed class DiskSpace
{
    private readonly TimeProvider _time;
    private readonly object _lock = new();
    private string? _path;
    private DateTimeOffset _at;
    private double _value;
    private bool _hasValue;

    public DiskSpace(TimeProvider time)
    {
        _time = time;
    }

    public double FreeGb(string path)
    {
        var key = path;
        var now = _time.GetUtcNow();
        lock (_lock)
        {
            if (_hasValue && _path == key &&
                now - _at < TimeSpan.FromSeconds(Limits.DiskCacheTtlSeconds))
            {
                return _value;
            }
        }

        var probe = path;
        while (!Directory.Exists(probe) && !File.Exists(probe))
        {
            var parent = Path.GetDirectoryName(probe);
            if (parent is null || parent == probe)
            {
                break;
            }

            probe = parent;
        }

        double value;
        try
        {
            var root = Path.GetPathRoot(Path.GetFullPath(probe));
            value = string.IsNullOrEmpty(root)
                ? 0.0
                : new DriveInfo(root).AvailableFreeSpace / 1e9;
        }
        catch (Exception ex) when (ex is IOException or ArgumentException or UnauthorizedAccessException)
        {
            // Unknown filesystem (e.g. a UNC path): treat as unknown and skip the check.
            value = 0.0;
        }

        lock (_lock)
        {
            _path = key;
            _at = now;
            _value = value;
            _hasValue = true;
        }

        return value;
    }

    public void Reset()
    {
        lock (_lock)
        {
            _hasValue = false;
            _path = null;
            _at = default;
            _value = 0.0;
        }
    }
}
