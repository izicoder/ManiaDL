using System.Globalization;
using ManiaDL.Core.Config;
using ManiaDL.Core.Constants;

namespace ManiaDL.Core.Api;

/// <summary>Port of api.build_query / minimal_query / search_params.</summary>
public static class QueryBuilder
{
    public static string Build(AppConfig cfg, int? key)
    {
        var parts = new List<string>();
        if (cfg.Query.Length > 0)
        {
            parts.Add(Parsing.QueryText.QueryTextValue(cfg.Query));
        }

        foreach (var value in new[] { cfg.Title, cfg.Artist, cfg.Creator, cfg.Source })
        {
            if (value.Length > 0)
            {
                parts.Add(Parsing.QueryText.QueryTextValue(value));
            }
        }

        if (key is not null)
        {
            parts.Add($"keys={key}");
        }

        if (cfg.MinSr > 0)
        {
            parts.Add($"stars>={FormatG(cfg.MinSr)}");
        }

        if (cfg.MaxSr < 99)
        {
            parts.Add($"stars<={FormatG(cfg.MaxSr)}");
        }

        if (cfg.MinBpm > 0)
        {
            parts.Add($"bpm>={FormatG(cfg.MinBpm)}");
        }

        if (cfg.MaxBpm < Limits.MaxBpm)
        {
            parts.Add($"bpm<={FormatG(cfg.MaxBpm)}");
        }

        if (cfg.MinLength > 0)
        {
            parts.Add($"length>={cfg.MinLength.ToString(CultureInfo.InvariantCulture)}");
        }

        if (cfg.MaxLength < Limits.MaxLength)
        {
            parts.Add($"length<={cfg.MaxLength.ToString(CultureInfo.InvariantCulture)}");
        }

        if (cfg.MinFavs > 0)
        {
            parts.Add($"favourites>={cfg.MinFavs.ToString(CultureInfo.InvariantCulture)}");
        }

        if (cfg.RankedAfter.Length > 0)
        {
            parts.Add($"ranked>={cfg.RankedAfter}");
        }

        if (cfg.RankedBefore.Length > 0)
        {
            parts.Add($"ranked<={cfg.RankedBefore}");
        }

        return string.Join(" ", parts.Where(part => part.Length > 0));
    }

    public static string Minimal(AppConfig cfg, int? key)
    {
        var parts = new List<string>();
        if (cfg.Query.Length > 0)
        {
            parts.Add(Parsing.QueryText.QueryTextValue(cfg.Query));
        }

        if (key is not null)
        {
            parts.Add($"keys={key}");
        }

        return string.Join(" ", parts.Where(part => part.Length > 0));
    }

    /// <summary>API parameters shared by the primary and fallback search.</summary>
    public static Dictionary<string, string> SearchParams(AppConfig cfg, int? key)
    {
        var parameters = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["m"] = "3",
            ["sort"] = cfg.Sort,
            ["nsfw"] = cfg.IncludeNsfw ? "true" : "false",
        };

        var query = Build(cfg, key);
        if (query.Length > 0)
        {
            parameters["q"] = query;
        }

        // The API takes a single genre/language id per request, so only narrow
        // server-side when the terms resolve to exactly one value.
        if (cfg.GenreIds.Count == 1)
        {
            parameters["g"] = cfg.GenreIds[0].ToString(CultureInfo.InvariantCulture);
        }

        if (cfg.LanguageIds.Count == 1)
        {
            parameters["l"] = cfg.LanguageIds[0].ToString(CultureInfo.InvariantCulture);
        }

        return parameters;
    }

    /// <summary>Python's <c>format(value, "g")</c> for the values used in queries.</summary>
    private static string FormatG(double value)
    {
        var text = value.ToString("G6", CultureInfo.InvariantCulture);
        return text.Replace('E', 'e');
    }
}
