using System.Text.Json.Serialization;

namespace ManiaDL.Core.Api;

/// <summary>
/// Search result DTO. Fields are nullable-tolerant so missing/null values behave
/// like Python's <c>.get(..., default)</c>.
/// </summary>
public sealed record Beatmapset
{
    [JsonPropertyName("id")] public long Id { get; init; }
    [JsonPropertyName("title")] public string? Title { get; init; }
    [JsonPropertyName("title_unicode")] public string? TitleUnicode { get; init; }
    [JsonPropertyName("artist")] public string? Artist { get; init; }
    [JsonPropertyName("artist_unicode")] public string? ArtistUnicode { get; init; }
    [JsonPropertyName("creator")] public string? Creator { get; init; }
    [JsonPropertyName("source")] public string? Source { get; init; }
    [JsonPropertyName("tags")] public string? Tags { get; init; }
    [JsonPropertyName("status")] public string? Status { get; init; }
    [JsonPropertyName("favourite_count")] public long? FavouriteCount { get; init; }
    [JsonPropertyName("play_count")] public long? PlayCount { get; init; }
    [JsonPropertyName("nsfw")] public bool? Nsfw { get; init; }
    [JsonPropertyName("bpm")] public double? Bpm { get; init; }
    [JsonPropertyName("genre_id")] public int? GenreId { get; init; }
    [JsonPropertyName("language_id")] public int? LanguageId { get; init; }
    [JsonPropertyName("ranked_date")] public string? RankedDate { get; init; }
    [JsonPropertyName("total_length")] public long? TotalLength { get; init; }
    [JsonPropertyName("beatmaps")] public List<Beatmap>? Beatmaps { get; init; }

    public string TitleOrEmpty => Title ?? "";
}

public sealed record Beatmap
{
    [JsonPropertyName("mode_int")] public int? ModeInt { get; init; }
    [JsonPropertyName("cs")] public double? Cs { get; init; }
    [JsonPropertyName("difficulty_rating")] public double? DifficultyRating { get; init; }
    [JsonPropertyName("count_circles")] public long? CountCircles { get; init; }
    [JsonPropertyName("count_sliders")] public long? CountSliders { get; init; }
    [JsonPropertyName("count_spinners")] public long? CountSpinners { get; init; }
    [JsonPropertyName("total_length")] public long? TotalLength { get; init; }
    [JsonPropertyName("version")] public string? Version { get; init; }
}
