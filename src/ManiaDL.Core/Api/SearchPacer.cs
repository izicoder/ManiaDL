using ManiaDL.Core.Constants;

namespace ManiaDL.Core.Api;

/// <summary>
/// Adaptive request pacer for the osu! API. The gap is measured from the start of
/// a request, so network latency is part of it instead of being added on top.
/// A 429 stretches the gap past Retry-After; successes shrink it back to base.
/// </summary>
public sealed class SearchPacer
{
    private readonly SemaphoreSlim _lock = new(1, 1);
    private readonly TimeProvider _time;
    private readonly Random _rng;
    private readonly double _base;
    private readonly double _ceiling;

    private double _interval;
    private DateTimeOffset _next = DateTimeOffset.MinValue;

    public SearchPacer(TimeProvider time, Random rng, double interval = Limits.SearchInterval)
    {
        _time = time;
        _rng = rng;
        _base = interval;
        _interval = interval;
        _ceiling = Limits.SearchMaxInterval;
    }

    public int Requests { get; private set; }

    public double Interval
    {
        get
        {
            lock (_lock)
            {
                return _interval;
            }
        }
    }

    public async Task WaitAsync(CancellationToken ct)
    {
        await _lock.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            var now = _time.GetUtcNow();
            if (_next > now)
            {
                await Task.Delay(_next - now, _time, ct).ConfigureAwait(false);
            }

            Requests++;
            var jitter = 1.0 + _rng.NextDouble() * Limits.SearchJitter;
            _next = _time.GetUtcNow() + TimeSpan.FromSeconds(_interval * jitter);
        }
        finally
        {
            _lock.Release();
        }
    }

    public void Success()
    {
        lock (_lock)
        {
            if (_interval > _base)
            {
                _interval = Math.Max(_base, _interval * 0.9);
            }
        }
    }

    /// <summary>Park the next request for at least <paramref name="seconds"/> and slow the pace.</summary>
    public void Penalise(double seconds)
    {
        seconds = Math.Max(0.0, seconds);
        lock (_lock)
        {
            _interval = Math.Min(_ceiling, Math.Max(_interval * 2, seconds));
            var now = _time.GetUtcNow();
            var parked = now + TimeSpan.FromSeconds(seconds);
            _next = parked > _next ? parked : _next;
        }
    }
}
