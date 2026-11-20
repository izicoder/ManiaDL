using System.Text.Encodings.Web;
using System.Text.Json;
using ManiaDL.Core.Constants;
using ManiaDL.Core.Logging;
using ManiaDL.Core.Parsing;
using ManiaDL.Core.Util;

namespace ManiaDL.Core.Config;

/// <summary>
/// Loads/saves <c>mania_dl_config.json</c> beside the executable, fills new keys
/// without touching existing values, and never throws on a bad file.
/// </summary>
public sealed class ConfigStore
{
    public static JsonSerializerOptions JsonOptions { get; } = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = true,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        Converters = { new LenientStringConverter(), new LenientBoolConverter() },
    };

    private readonly AppPaths _paths;

    public ConfigStore(AppPaths paths)
    {
        _paths = paths;
    }

    public string Path => _paths.ConfigPath;

    public RawConfig Load()
    {
        try
        {
            var text = File.ReadAllText(_paths.ConfigPath);
            using var document = JsonDocument.Parse(text);
            if (document.RootElement.ValueKind != JsonValueKind.Object)
            {
                return new RawConfig();
            }

            var config = JsonSerializer.Deserialize<RawConfig>(text, JsonOptions);
            if (config is null)
            {
                return new RawConfig();
            }

            config.PresentKeys = document.RootElement.EnumerateObject()
                .Select(property => property.Name)
                .ToHashSet(StringComparer.Ordinal);
            return config;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
        {
            return new RawConfig();
        }
    }

    /// <summary>Load and migrate, reporting whether a save is warranted.</summary>
    public (RawConfig Config, bool Changed) LoadAndMigrate()
    {
        var config = Load();
        var changed = Migrate(config);
        return (config, changed);
    }

    /// <summary>Fill new optional keys and drop retired ones; preserve everything else.</summary>
    public static bool Migrate(RawConfig config)
    {
        var changed = false;

        if (config.Extra is not null)
        {
            // safe_mode was an internal pacing toggle that briefly leaked into config.
            if (config.Extra.Remove("safe_mode")) changed = true;
            if (config.Extra.Remove("slide_window")) changed = true;
        }

        foreach (var key in Lookups.NewSettingKeys)
        {
            if (config.PresentKeys.Contains(key))
            {
                continue;
            }

            ApplyDefault(config, key, Lookups.NewDefaults[key]);
            config.PresentKeys.Add(key);
            changed = true;
        }

        return changed;
    }

    private static void ApplyDefault(RawConfig config, string key, object? value)
    {
        switch (key)
        {
            case "advanced": config.Advanced = TextParser.AsBool(value); break;
            case "query": config.Query = TextParser.AsText(value); break;
            case "title": config.Title = TextParser.AsText(value); break;
            case "artist": config.Artist = TextParser.AsText(value); break;
            case "creator": config.Creator = TextParser.AsText(value); break;
            case "source": config.Source = TextParser.AsText(value); break;
            case "exclude": config.Exclude = TextParser.AsText(value); break;
            case "genre": config.Genre = TextParser.AsText(value); break;
            case "language": config.Language = TextParser.AsText(value); break;
            case "bpm_range": config.BpmRange = TextParser.AsText(value); break;
            case "length_range": config.LengthRange = TextParser.AsText(value); break;
            case "notes_range": config.NotesRange = TextParser.AsText(value); break;
            case "min_plays": config.MinPlays = TextParser.AsText(value); break;
            case "ranked_range": config.RankedRange = TextParser.AsText(value); break;
            case "include_nsfw": config.IncludeNsfw = TextParser.AsBool(value); break;
        }
    }

    public bool Save(RawConfig config, RunLog? log = null)
    {
        try
        {
            var json = JsonSerializer.Serialize(config, JsonOptions);
            AtomicFile.WriteText(_paths.ConfigPath, json);
            return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            log?.Warning($"Couldn't save settings: {ex.Message}");
            return false;
        }
    }
}
