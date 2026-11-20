using ManiaDL.Core.Logging;
using ManiaDL.Core.Progress;
using ManiaDL.Core.Util;

namespace ManiaDL.Core.Run;

public readonly record struct StatsSnapshot(long Ok, long Fail, long Active, long Bytes);

/// <summary>Interlocked-only run counters.</summary>
public sealed class RunStats
{
    private long _ok;
    private long _fail;
    private long _active;
    private long _bytes;

    public void AddOk() => Interlocked.Increment(ref _ok);
    public void AddFail() => Interlocked.Increment(ref _fail);
    public void AddActive(int delta) => Interlocked.Add(ref _active, delta);
    public void AddBytes(long count) => Interlocked.Add(ref _bytes, count);

    public StatsSnapshot Snapshot() => new(
        Volatile.Read(ref _ok),
        Volatile.Read(ref _fail),
        Volatile.Read(ref _active),
        Volatile.Read(ref _bytes));
}

/// <summary>
/// Per-run state. A new instance is created for every Start press; nothing is
/// static or shared between runs. Replaces Python's mutable runtime module.
/// </summary>
public sealed class RunContext
{
    private volatile bool _mirrorsExhausted;

    public RunContext(
        CancellationTokenSource stop,
        RunLog log,
        TaskBoard progress,
        TimeProvider time,
        Random rng)
    {
        Stop = stop;
        Log = log;
        Progress = progress;
        Time = time;
        Rng = rng;
        Mirrors = new MirrorStats(rng);
        Hosts = new HostGates(time, rng);
        Disk = new DiskSpace(time);
    }

    public CancellationTokenSource Stop { get; }
    public RunStats Stats { get; } = new();
    public MirrorStats Mirrors { get; }
    public HostGates Hosts { get; }
    public TaskBoard Progress { get; }
    public RunLog Log { get; }
    public TimeProvider Time { get; }
    public Random Rng { get; }
    public DiskSpace Disk { get; }
    public CancellationToken Token => Stop.Token;

    public bool MirrorsExhausted
    {
        get => _mirrorsExhausted;
        set => _mirrorsExhausted = value;
    }
}
