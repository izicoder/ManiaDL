using System.Collections.Concurrent;
using ManiaDL.Core.Constants;

namespace ManiaDL.Core.Run;

/// <summary>
/// Per-host request gate: space request starts, then cap concurrent streams.
/// Requests are spaced from the start (not the response), exactly like mirrors.py.
/// </summary>
public sealed class HostGate
{
    private readonly SemaphoreSlim _spacing = new(1, 1);
    private readonly SemaphoreSlim _concurrency = new(Limits.HostConcurrency);
    private readonly TimeProvider _time;
    private readonly Random _rng;
    private long _lastStart;
    private bool _started;
    private int _inflight;

    public HostGate(TimeProvider time, Random rng)
    {
        _time = time;
        _rng = rng;
    }

    public int Inflight => Volatile.Read(ref _inflight);

    /// <summary>Waits for this host's turn and a concurrency slot; dispose to release.</summary>
    public async Task<IDisposable> AcquireAsync(CancellationToken ct)
    {
        await _spacing.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            var jitter = Limits.HostJitterLow +
                         _rng.NextDouble() * (Limits.HostJitterHigh - Limits.HostJitterLow);
            var interval = Limits.HostInterval * jitter;
            if (_started)
            {
                var elapsed = _time.GetElapsedTime(_lastStart, _time.GetTimestamp()).TotalSeconds;
                var wait = interval - elapsed;
                if (wait > 0)
                {
                    await Task.Delay(TimeSpan.FromSeconds(wait), _time, ct).ConfigureAwait(false);
                }
            }

            _lastStart = _time.GetTimestamp();
            _started = true;
        }
        finally
        {
            _spacing.Release();
        }

        await _concurrency.WaitAsync(ct).ConfigureAwait(false);
        Interlocked.Increment(ref _inflight);
        return new Releaser(this);
    }

    private sealed class Releaser : IDisposable
    {
        private readonly HostGate _gate;
        private int _disposed;

        public Releaser(HostGate gate)
        {
            _gate = gate;
        }

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _disposed, 1) != 0)
            {
                return;
            }

            Interlocked.Decrement(ref _gate._inflight);
            _gate._concurrency.Release();
        }
    }
}

/// <summary>Lazily created gate per mirror host (catboy and catboy-video share one).</summary>
public sealed class HostGates
{
    private readonly ConcurrentDictionary<string, HostGate> _gates =
        new(StringComparer.OrdinalIgnoreCase);

    private readonly TimeProvider _time;
    private readonly Random _rng;

    public HostGates(TimeProvider time, Random rng)
    {
        _time = time;
        _rng = rng;
    }

    public HostGate For(string host) => _gates.GetOrAdd(host, key => new HostGate(_time, _rng));

    public int Inflight(string host) =>
        _gates.TryGetValue(host, out var gate) ? gate.Inflight : 0;
}
