using System.Threading.Channels;
using ManiaDL.Core.Config;
using ManiaDL.Core.Logging;

namespace ManiaDL.Core.Engine;

public enum EngineState
{
    Idle,
    Running,
    Stopping,
}

public readonly record struct StartOutcome(bool Started, string? Error, string? Field)
{
    public static StartOutcome Ok() => new(true, null, null);
    public static StartOutcome Fail(string error, string? field = null) => new(false, error, field);
}

public abstract record EngineEvent;

/// <summary>State name is one of idle, running, stopping, done, stopped, paused, error.</summary>
public sealed record StateChangedEvent(string State, string? Detail = null) : EngineEvent;

public sealed record LogBatchEvent(IReadOnlyList<LogEntry> Entries) : EngineEvent;

public sealed record ProgressEvent(ProgressDto Value) : EngineEvent;

public sealed record DoneEvent(RunResultDto Result) : EngineEvent;

public sealed record EngineErrorEvent(string Message, string? Field = null) : EngineEvent;

public sealed record RowDto(string Label, string Value);

public sealed record LinkDto(string Name, string Url);

public sealed record FailedDto(long Id, string Title, IReadOnlyList<LinkDto> Links);

public sealed record TaskDto(int Id, string Description, double Completed, double? Total);

public sealed record OverallDto(double Completed, double Total, double Percent);

public sealed record StatsDto(
    long Ok, long Fail, long Active, long Bytes, double SpeedBytesPerSecond);

public sealed record ProgressDto(
    string Message,
    OverallDto Overall,
    IReadOnlyList<TaskDto> Active,
    StatsDto Stats,
    double FreeGb);

/// <summary>Everything the UI needs from a finished run, already formatted.</summary>
public sealed record RunResultDto(
    string State,
    string Footer,
    IReadOnlyList<RowDto> Summary,
    IReadOnlyList<FailedDto> Failed,
    int Matched,
    int Todo,
    int Existing,
    bool Stopped,
    bool MirrorsExhausted,
    double Elapsed,
    StatsDto Stats);

public interface IEngine
{
    EngineState State { get; }
    Task<StartOutcome> StartAsync(RawConfig raw);
    void Stop();
    ChannelReader<EngineEvent> Events { get; }
}
