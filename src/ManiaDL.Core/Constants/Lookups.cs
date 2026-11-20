namespace ManiaDL.Core.Constants;

/// <summary>Domain tables (statuses, genres, languages, sorts and setting keys).</summary>
public static class Lookups
{
    public static IReadOnlyDictionary<string, IReadOnlySet<string>> StatusSets { get; } =
        new Dictionary<string, IReadOnlySet<string>>(StringComparer.Ordinal)
        {
            ["graveyard"] = new HashSet<string> { "graveyard" },
            ["ranked"] = new HashSet<string> { "ranked", "approved" },
            ["loved"] = new HashSet<string> { "loved" },
            ["qualified"] = new HashSet<string> { "qualified" },
            ["pending"] = new HashSet<string> { "pending", "wip" },
        };

    /// <summary>What to send to the osu! API for each user-facing status.</summary>
    public static IReadOnlyDictionary<string, IReadOnlyList<string>> ApiStatuses { get; } =
        new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal)
        {
            ["graveyard"] = new[] { "graveyard" },
            ["ranked"] = new[] { "ranked" },
            ["loved"] = new[] { "loved" },
            ["qualified"] = new[] { "qualified" },
            ["pending"] = new[] { "pending", "wip" },
        };

    public static IReadOnlyList<string> Sorts { get; } = new[]
    {
        "favourites_desc",
        "plays_desc",
        "ranked_desc",
        "updated_desc",
        "difficulty_desc",
        "relevance_desc",
    };

    public static IReadOnlyDictionary<string, string> SortLabels { get; } =
        new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["favourites_desc"] = "Most favourites",
            ["plays_desc"] = "Most played",
            ["ranked_desc"] = "Recently ranked",
            ["updated_desc"] = "Recently updated",
            ["difficulty_desc"] = "Difficulty",
            ["relevance_desc"] = "Relevance",
        };

    /// <summary>Status order used by the GUI checkboxes.</summary>
    public static IReadOnlyList<string> StatusOrder { get; } =
        new[] { "ranked", "loved", "qualified", "pending", "graveyard" };

    public static IReadOnlyDictionary<string, int> GenreIds { get; } =
        new Dictionary<string, int>(StringComparer.Ordinal)
        {
            ["video game"] = 2,
            ["anime"] = 3,
            ["rock"] = 4,
            ["pop"] = 5,
            ["other"] = 6,
            ["novelty"] = 7,
            ["hip hop"] = 9,
            ["electronic"] = 10,
            ["metal"] = 11,
            ["classical"] = 12,
            ["folk"] = 13,
            ["jazz"] = 14,
            ["unspecified"] = 1,
        };

    public static IReadOnlyDictionary<string, int> LanguageIds { get; } =
        new Dictionary<string, int>(StringComparer.Ordinal)
        {
            ["english"] = 2,
            ["japanese"] = 3,
            ["chinese"] = 4,
            ["instrumental"] = 5,
            ["korean"] = 6,
            ["french"] = 7,
            ["german"] = 8,
            ["swedish"] = 9,
            ["spanish"] = 10,
            ["italian"] = 11,
            ["russian"] = 12,
            ["polish"] = 13,
            ["other"] = 14,
            ["unspecified"] = 1,
        };

    /// <summary>Legacy keys that older notes called a "reuse gate"; unused by current code.</summary>
    public static IReadOnlyList<string> SettingKeys { get; } = new[]
    {
        "out", "statuses", "keys", "min_sr", "max_sr", "min_favs", "sort",
        "limit", "workers", "batch",
    };

    public static IReadOnlyList<string> NewSettingKeys { get; } = new[]
    {
        "advanced", "query", "title", "artist", "creator", "source", "exclude",
        "genre", "language", "bpm_range", "length_range", "notes_range",
        "min_plays", "ranked_range", "include_nsfw",
    };

    public static IReadOnlyList<string> AdvancedKeys { get; } = new[]
    {
        "query", "title", "artist", "creator", "source", "exclude", "genre",
        "language", "bpm_range", "length_range", "notes_range", "min_plays",
        "ranked_range", "include_nsfw",
    };

    /// <summary>Defaults for <see cref="NewSettingKeys"/>, filled on first run of this version.</summary>
    public static IReadOnlyDictionary<string, object?> NewDefaults { get; } =
        new Dictionary<string, object?>(StringComparer.Ordinal)
        {
            ["advanced"] = false,
            ["query"] = "",
            ["title"] = "",
            ["artist"] = "",
            ["creator"] = "",
            ["source"] = "",
            ["exclude"] = "",
            ["genre"] = "",
            ["language"] = "",
            ["bpm_range"] = "",
            ["length_range"] = "",
            ["notes_range"] = "",
            ["min_plays"] = 0,
            ["ranked_range"] = "",
            ["include_nsfw"] = false,
        };
}
