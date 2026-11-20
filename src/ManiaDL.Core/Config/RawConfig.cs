using System.Text.Json;
using System.Text.Json.Serialization;
using ManiaDL.Core.Parsing;

namespace ManiaDL.Core.Config;

/// <summary>
/// The raw settings the UI edits and <c>mania_dl_config.json</c> stores: mostly
/// strings, exactly like the Python widget values. Unknown keys are preserved.
/// </summary>
public sealed class RawConfig
{
    [JsonPropertyName("client_id")] public string ClientId { get; set; } = "";
    [JsonPropertyName("client_secret")] public string ClientSecret { get; set; } = "";

    [JsonPropertyName("out")] public string Out { get; set; } = "";
    [JsonPropertyName("statuses")] public string Statuses { get; set; } = "ranked";
    [JsonPropertyName("keys")] public string Keys { get; set; } = "all";
    [JsonPropertyName("min_sr")] public string MinSr { get; set; } = "0";
    [JsonPropertyName("max_sr")] public string MaxSr { get; set; } = "99";
    [JsonPropertyName("min_favs")] public string MinFavs { get; set; } = "0";
    [JsonPropertyName("sort")] public string Sort { get; set; } = "favourites_desc";
    [JsonPropertyName("limit")] public string Limit { get; set; } = "500";
    [JsonPropertyName("workers")] public string Workers { get; set; } = "4";
    [JsonPropertyName("batch")] public string Batch { get; set; } = "20";

    [JsonPropertyName("advanced")] public bool Advanced { get; set; }

    [JsonPropertyName("query")] public string Query { get; set; } = "";
    [JsonPropertyName("title")] public string Title { get; set; } = "";
    [JsonPropertyName("artist")] public string Artist { get; set; } = "";
    [JsonPropertyName("creator")] public string Creator { get; set; } = "";
    [JsonPropertyName("source")] public string Source { get; set; } = "";
    [JsonPropertyName("exclude")] public string Exclude { get; set; } = "";
    [JsonPropertyName("genre")] public string Genre { get; set; } = "";
    [JsonPropertyName("language")] public string Language { get; set; } = "";
    [JsonPropertyName("bpm_range")] public string BpmRange { get; set; } = "";
    [JsonPropertyName("length_range")] public string LengthRange { get; set; } = "";
    [JsonPropertyName("notes_range")] public string NotesRange { get; set; } = "";
    [JsonPropertyName("min_plays")] public string MinPlays { get; set; } = "0";
    [JsonPropertyName("ranked_range")] public string RankedRange { get; set; } = "";
    [JsonPropertyName("include_nsfw")] public bool IncludeNsfw { get; set; }

    /// <summary>Unknown keys from older or newer builds; written back unchanged.</summary>
    [JsonExtensionData] public Dictionary<string, JsonElement>? Extra { get; set; }

    /// <summary>Keys present in the loaded file, used to drive the migration.</summary>
    [JsonIgnore] public HashSet<string> PresentKeys { get; set; } = new(StringComparer.Ordinal);

    public RawConfig Clone()
    {
        var clone = (RawConfig)MemberwiseClone();
        clone.Extra = Extra is null
            ? null
            : Extra.ToDictionary(pair => pair.Key, pair => pair.Value);
        clone.PresentKeys = new HashSet<string>(PresentKeys, StringComparer.Ordinal);
        return clone;
    }

    /// <summary>Copy UI-editable values onto this instance, keeping unknown keys.</summary>
    public void CopyFrom(RawConfig other)
    {
        ClientId = other.ClientId;
        ClientSecret = other.ClientSecret;
        Out = other.Out;
        Statuses = other.Statuses;
        Keys = other.Keys;
        MinSr = other.MinSr;
        MaxSr = other.MaxSr;
        MinFavs = other.MinFavs;
        Sort = other.Sort;
        Limit = other.Limit;
        Workers = other.Workers;
        Batch = other.Batch;
        Advanced = other.Advanced;
        Query = other.Query;
        Title = other.Title;
        Artist = other.Artist;
        Creator = other.Creator;
        Source = other.Source;
        Exclude = other.Exclude;
        Genre = other.Genre;
        Language = other.Language;
        BpmRange = other.BpmRange;
        LengthRange = other.LengthRange;
        NotesRange = other.NotesRange;
        MinPlays = other.MinPlays;
        RankedRange = other.RankedRange;
        IncludeNsfw = other.IncludeNsfw;
    }
}

/// <summary>Accepts both JSON strings and numbers for the string-typed settings.</summary>
public sealed class LenientStringConverter : JsonConverter<string>
{
    public override string Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) =>
        reader.TokenType switch
        {
            JsonTokenType.String => reader.GetString() ?? "",
            JsonTokenType.Number => reader.TryGetInt64(out var number)
                ? number.ToString(System.Globalization.CultureInfo.InvariantCulture)
                : reader.GetDouble().ToString("R", System.Globalization.CultureInfo.InvariantCulture),
            JsonTokenType.True => "true",
            JsonTokenType.False => "false",
            JsonTokenType.Null => "",
            _ => throw new JsonException($"Unexpected token {reader.TokenType} for a text setting."),
        };

    public override void Write(Utf8JsonWriter writer, string value, JsonSerializerOptions options) =>
        writer.WriteStringValue(value);
}

/// <summary>Accepts true/false, 0/1 and "yes"/"on"-style strings for boolean settings.</summary>
public sealed class LenientBoolConverter : JsonConverter<bool>
{
    public override bool Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) =>
        reader.TokenType switch
        {
            JsonTokenType.True => true,
            JsonTokenType.False => false,
            JsonTokenType.Number => reader.TryGetInt64(out var number) ? number != 0 : reader.GetDouble() != 0,
            JsonTokenType.String => TextParser.AsBool(reader.GetString()),
            JsonTokenType.Null => false,
            _ => throw new JsonException($"Unexpected token {reader.TokenType} for a boolean setting."),
        };

    public override void Write(Utf8JsonWriter writer, bool value, JsonSerializerOptions options) =>
        writer.WriteBooleanValue(value);
}
