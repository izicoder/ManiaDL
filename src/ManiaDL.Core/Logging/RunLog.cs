using System.Threading.Channels;
using ManiaDL.Core.Constants;

namespace ManiaDL.Core.Logging;

public enum LogLevel
{
    Info,
    Success,
    Warning,
    Error,
    Muted,
}

public readonly record struct LogEntry(DateTimeOffset Time, LogLevel Level, string Message)
{
    /// <summary>Display form: local HH:mm:ss, two spaces, message.</summary>
    public string Display => $"{Time:HH:mm:ss}  {Message}";

    /// <summary>Lower-case level name used by the bridge protocol.</summary>
    public string LevelName => Level.ToString().ToLowerInvariant();
}

/// <summary>
/// Structured log feed. The engine writes entries; the host drains the channel and
/// forwards batches to the UI. A 500-entry ring keeps lines for a late subscriber.
/// No rich-markup tags and no string re-classification.
/// </summary>
public sealed class RunLog
{
    private readonly object _lock = new();
    private readonly Queue<LogEntry> _ring = new();
    private readonly Channel<LogEntry> _channel =
        Channel.CreateUnbounded<LogEntry>(new UnboundedChannelOptions { SingleReader = true });

    private readonly TimeProvider _time;

    public RunLog(TimeProvider time)
    {
        _time = time;
    }

    public ChannelReader<LogEntry> Reader => _channel.Reader;

    public void Info(string message) => Write(LogLevel.Info, message);
    public void Success(string message) => Write(LogLevel.Success, message);
    public void Warning(string message) => Write(LogLevel.Warning, message);
    public void Error(string message) => Write(LogLevel.Error, message);
    public void Muted(string message) => Write(LogLevel.Muted, message);

    public void Write(LogLevel level, string message)
    {
        var entry = new LogEntry(_time.GetLocalNow(), level, message);
        lock (_lock)
        {
            _ring.Enqueue(entry);
            while (_ring.Count > Limits.LogRingSize)
            {
                _ring.Dequeue();
            }
        }

        _channel.Writer.TryWrite(entry);
    }

    public IReadOnlyList<LogEntry> Recent()
    {
        lock (_lock)
        {
            return _ring.ToArray();
        }
    }

    public void Complete() => _channel.Writer.TryComplete();
}
