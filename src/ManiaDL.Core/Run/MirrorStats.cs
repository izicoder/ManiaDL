using System.Collections.Concurrent;

namespace ManiaDL.Core.Run;

public readonly record struct MirrorSnapshot(
    long Ok, long Fail, long Streak, DateTimeOffset Until, DateTimeOffset Last);

/// <summary>Per-mirror health. Every field is guarded by the state's own lock.</summary>
public sealed class MirrorState
{
    private readonly object _lock = new();
    private long _ok;
    private long _fail;
    private long _streak;
    private DateTimeOffset _until;
    private DateTimeOffset _last;

    public MirrorSnapshot Snapshot()
    {
        lock (_lock)
        {
            return new MirrorSnapshot(_ok, _fail, _streak, _until, _last);
        }
    }

    public DateTimeOffset Until
    {
        get
        {
            lock (_lock)
            {
                return _until;
            }
        }
    }

    public void MarkChosen(DateTimeOffset now)
    {
        lock (_lock)
        {
            _last = now;
        }
    }

    public void MarkOk()
    {
        lock (_lock)
        {
            _ok++;
            _streak = 0;
            _until = default;
        }
    }

    public void MarkMiss()
    {
        lock (_lock)
        {
            _fail++;
            _streak++;
        }
    }

    public void Park(DateTimeOffset until)
    {
        lock (_lock)
        {
            _until = until;
            _streak++;
        }
    }
}

public sealed class MirrorStats
{
    private readonly ConcurrentDictionary<string, MirrorState> _states = new(StringComparer.Ordinal);
    private readonly Random _rng;

    public MirrorStats(Random rng)
    {
        _rng = rng;
    }

    public MirrorState State(string name) => _states.GetOrAdd(name, _ => new MirrorState());

    /// <summary>Parks every mirror sharing this host; returns the new park-until time.</summary>
    public DateTimeOffset ParkHost(
        string host,
        IReadOnlyList<Constants.Mirror> mirrors,
        int seconds,
        DateTimeOffset now,
        out TimeSpan wait)
    {
        var clamped = Math.Min(Math.Max(seconds, 30), Constants.Limits.MaxRetryAfterSeconds);
        var jitter = _rng.NextDouble() * 5.0;
        var until = now.AddSeconds(clamped + jitter);
        foreach (var mirror in mirrors.Where(mirror => mirror.Host == host))
        {
            State(mirror.Name).Park(until);
        }

        wait = until - now;
        return until;
    }
}
