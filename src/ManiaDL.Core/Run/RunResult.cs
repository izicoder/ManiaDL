namespace ManiaDL.Core.Run;

/// <summary>Everything the old GUI needed from a finished run.</summary>
public sealed record RunResult
{
    public required int Matched { get; init; }
    public required int Existing { get; init; }
    public required int Todo { get; init; }
    public required IReadOnlyDictionary<long, string> Failed { get; init; }
    public required IReadOnlyDictionary<long, string> NewFailed { get; init; }
    public required IReadOnlyDictionary<long, string> Titles { get; init; }
    public required double Elapsed { get; init; }
    public required bool Stopped { get; init; }
    public required bool MirrorsExhausted { get; init; }
}
