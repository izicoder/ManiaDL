using ManiaDL.Core.Constants;

namespace ManiaDL.Core.Config;

/// <summary>A user-facing configuration error (safe to show in the UI).</summary>
public sealed class ConfigException : Exception
{
    public ConfigException(string message) : base(message)
    {
    }
}

/// <summary>Validated, typed, immutable configuration consumed by the core.</summary>
public sealed record AppConfig
{
    public required string Out { get; init; }
    public required IReadOnlyList<string> Statuses { get; init; }
    public required IReadOnlyList<int>? Keys { get; init; }
    public required double MinSr { get; init; }
    public required double MaxSr { get; init; }
    public required int MinFavs { get; init; }
    public required string Sort { get; init; }
    public required int Limit { get; init; }
    public required int Workers { get; init; }
    public required int Batch { get; init; }
    public required bool Advanced { get; init; }

    public required string Query { get; init; }
    public required string Title { get; init; }
    public required string Artist { get; init; }
    public required string Creator { get; init; }
    public required string Source { get; init; }
    public required IReadOnlyList<string> Exclude { get; init; }
    public required IReadOnlyList<string> Genre { get; init; }
    public required IReadOnlyList<string> Language { get; init; }
    public required int MinPlays { get; init; }
    public required bool IncludeNsfw { get; init; }

    public required double MinBpm { get; init; }
    public required double MaxBpm { get; init; }
    public required int MinLength { get; init; }
    public required int MaxLength { get; init; }
    public required int MinNotes { get; init; }
    public required int MaxNotes { get; init; }
    public required string RankedAfter { get; init; }
    public required string RankedBefore { get; init; }

    public required IReadOnlyList<int> GenreIds { get; init; }
    public required IReadOnlyList<int> LanguageIds { get; init; }
    public required IReadOnlyList<string> QueryTerms { get; init; }

    /// <summary>Null means "any status"; otherwise the accepted raw osu! statuses.</summary>
    public required IReadOnlySet<string>? AllowedStatuses { get; init; }

    public bool StatusAllowed(string value)
    {
        if (AllowedStatuses is null)
        {
            if (Statuses.Contains("any"))
            {
                return true;
            }

            var union = new HashSet<string>(StringComparer.Ordinal);
            foreach (var status in Statuses)
            {
                union.UnionWith(Lookups.StatusSets[status]);
            }

            return union.Contains(value);
        }

        return AllowedStatuses.Contains(value);
    }
}
