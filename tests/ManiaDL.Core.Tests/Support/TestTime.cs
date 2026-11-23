using System.Diagnostics;

namespace ManiaDL.Core.Tests.Support;

/// <summary>
/// A <see cref="TimeProvider"/> whose clock only moves when a test calls
/// <see cref="Advance"/>. Timers fire during <see cref="Advance"/>.
/// </summary>
public sealed class ManualTimeProvider : TimeProvider, IDisposable
{
    private readonly object _gate = new();
    private readonly List<ManualTimer> _timers = new();
    private DateTimeOffset _now;
    private bool _disposed;

    public ManualTimeProvider(DateTimeOffset? start = null) =>
        _now = start ?? new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);

    public override DateTimeOffset GetUtcNow()
    {
        lock (_gate)
        {
            return _now;
        }
    }

    public override long TimestampFrequency => TimeSpan.TicksPerSecond;

    public override long GetTimestamp()
    {
        lock (_gate)
        {
            return _now.UtcTicks;
        }
    }

    public override ITimer CreateTimer(
        TimerCallback callback, object? state, TimeSpan dueTime, TimeSpan period)
    {
        var timer = new ManualTimer(callback, state);
        lock (_gate)
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            timer.Set(_now, dueTime, period);
            _timers.Add(timer);
        }

        return timer;
    }

    /// <summary>Moves the clock forward and fires every timer that became due.</summary>
    public void Advance(TimeSpan delta)
    {
        List<ManualTimer> due;
        lock (_gate)
        {
            _now += delta;
            due = _timers.Where(timer => timer.IsDue(_now)).ToList();
            foreach (var timer in due)
            {
                timer.Reschedule(_now);
            }
        }

        foreach (var timer in due)
        {
            timer.Fire();
        }
    }

    public void Dispose()
    {
        lock (_gate)
        {
            _disposed = true;
            _timers.Clear();
        }
    }

    private sealed class ManualTimer : ITimer
    {
        private readonly TimerCallback _callback;
        private readonly object? _state;
        private DateTimeOffset _dueAt = DateTimeOffset.MaxValue;
        private TimeSpan _period;
        private bool _completed;
        private bool _disposed;

        public ManualTimer(TimerCallback callback, object? state)
        {
            _callback = callback;
            _state = state;
        }

        public void Set(DateTimeOffset now, TimeSpan dueTime, TimeSpan period)
        {
            _period = period;
            _dueAt = dueTime == Timeout.InfiniteTimeSpan ? DateTimeOffset.MaxValue : now + dueTime;
            _completed = false;
        }

        public bool IsDue(DateTimeOffset now) =>
            !_disposed && !_completed && now >= _dueAt;

        public void Reschedule(DateTimeOffset now)
        {
            if (_period > TimeSpan.Zero)
            {
                _dueAt = now + _period;
            }
            else
            {
                _completed = true;
            }
        }

        public void Fire()
        {
            if (!_disposed)
            {
                _callback(_state);
            }
        }

        public bool Change(TimeSpan dueTime, TimeSpan period)
        {
            _period = period;
            _dueAt = dueTime == Timeout.InfiniteTimeSpan
                ? DateTimeOffset.MaxValue
                : DateTimeOffset.UtcNow + dueTime;
            _completed = false;
            return true;
        }

        public void Dispose() => _disposed = true;

        public ValueTask DisposeAsync()
        {
            Dispose();
            return ValueTask.CompletedTask;
        }
    }
}

/// <summary>
/// A <see cref="TimeProvider"/> with a real clock but zero-length delays. Used by
/// download/orchestration tests so retries and batch pauses do not sleep.
/// </summary>
public sealed class ImmediateTimeProvider : TimeProvider
{
    public override DateTimeOffset GetUtcNow() => DateTimeOffset.UtcNow;

    public override long TimestampFrequency => Stopwatch.Frequency;

    public override long GetTimestamp() => Stopwatch.GetTimestamp();

    public override ITimer CreateTimer(
        TimerCallback callback, object? state, TimeSpan dueTime, TimeSpan period)
    {
        var timer = new OneShotTimer();

        // Retry/backoff delays fire immediately so tests do not sleep. Long
        // timeouts (read = 120 s, file = 900 s) are left pending on purpose:
        // they must not cancel a fake transfer that finishes instantly.
        if (dueTime != Timeout.InfiniteTimeSpan && dueTime <= TimeSpan.FromMinutes(5))
        {
            ThreadPool.QueueUserWorkItem(_ =>
            {
                if (!timer.Disposed)
                {
                    callback(state);
                }
            });
        }

        return timer;
    }

    private sealed class OneShotTimer : ITimer
    {
        public bool Disposed { get; private set; }

        public bool Change(TimeSpan dueTime, TimeSpan period) => true;

        public void Dispose() => Disposed = true;

        public ValueTask DisposeAsync()
        {
            Dispose();
            return ValueTask.CompletedTask;
        }
    }
}

public static class TestClock
{
    /// <summary>
    /// Advances a manual clock until <paramref name="task"/> completes, yielding
    /// between steps so continuations can register their timers.
    /// </summary>
    public static async Task AdvanceUntilAsync(
        ManualTimeProvider time,
        Task task,
        TimeSpan? step = null,
        int maxSteps = 2000)
    {
        var increment = step ?? TimeSpan.FromSeconds(1);
        var steps = 0;
        while (!task.IsCompleted)
        {
            if (++steps > maxSteps)
            {
                throw new TimeoutException("The task did not finish while the test clock advanced.");
            }

            time.Advance(increment);
            await Task.Delay(1);
        }

        await task;
    }

    public static async Task<T> AdvanceUntilAsync<T>(
        ManualTimeProvider time,
        Task<T> task,
        TimeSpan? step = null,
        int maxSteps = 2000)
    {
        await AdvanceUntilAsync(time, (Task)task, step, maxSteps);
        return await task;
    }
}
