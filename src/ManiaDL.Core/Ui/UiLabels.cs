using System.Globalization;
using ManiaDL.Core.Config;
using ManiaDL.Core.Constants;

namespace ManiaDL.Core.Ui;

/// <summary>Port of ui.py: human-readable labels for the GUI.</summary>
public static class UiLabels
{
    public static string RangeLabel(
        double low, double high, double lowDefault, double highDefault, string unit = "")
    {
        if (low <= lowDefault && high >= highDefault)
        {
            return "any";
        }

        if (low > lowDefault && high < highDefault)
        {
            return $"{FormatG(low)}-{FormatG(high)}{unit}";
        }

        if (low > lowDefault)
        {
            return $">={FormatG(low)}{unit}";
        }

        return $"<={FormatG(high)}{unit}";
    }

    public static string DateLabel(string after, string before)
    {
        if (after.Length > 0 && before.Length > 0)
        {
            return $"{after}..{before}";
        }

        if (after.Length > 0)
        {
            return $">={after}";
        }

        if (before.Length > 0)
        {
            return $"<={before}";
        }

        return "any";
    }

    public static string KeysLabel(AppConfig cfg) =>
        cfg.Keys is null ? "all" : string.Join(", ", cfg.Keys.Select(key => $"{key}K"));

    public static IReadOnlyList<(string Key, string Value)> SummaryRows(AppConfig cfg)
    {
        var rows = new List<(string, string)>
        {
            ("Download folder", cfg.Out),
            ("Status", string.Join(", ", cfg.Statuses)),
            ("Keys", KeysLabel(cfg)),
            ("Star rating", $"{FormatG(cfg.MinSr)} - {FormatG(cfg.MaxSr)}"),
            ("Min favourites", cfg.MinFavs.ToString(CultureInfo.InvariantCulture)),
            ("Sort", Lookups.SortLabels.TryGetValue(cfg.Sort, out var label) ? label : cfg.Sort),
            ("Max sets", cfg.Limit.ToString(CultureInfo.InvariantCulture)),
            ("Parallel / batch",
                $"{cfg.Workers.ToString(CultureInfo.InvariantCulture)} / {cfg.Batch.ToString(CultureInfo.InvariantCulture)}"),
        };

        if (!cfg.Advanced)
        {
            return rows;
        }

        rows.AddRange(new (string, string)[]
        {
            ("Query", cfg.Query.Length > 0 ? cfg.Query : "-"),
            ("Title contains", cfg.Title.Length > 0 ? cfg.Title : "-"),
            ("Artist contains", cfg.Artist.Length > 0 ? cfg.Artist : "-"),
            ("Creator contains", cfg.Creator.Length > 0 ? cfg.Creator : "-"),
            ("Source contains", cfg.Source.Length > 0 ? cfg.Source : "-"),
            ("Exclude", cfg.Exclude.Count > 0 ? string.Join(", ", cfg.Exclude) : "-"),
            ("Genre", cfg.Genre.Count > 0 ? string.Join(", ", cfg.Genre) : "any"),
            ("Language", cfg.Language.Count > 0 ? string.Join(", ", cfg.Language) : "any"),
            ("BPM", RangeLabel(cfg.MinBpm, cfg.MaxBpm, 0.0, Limits.MaxBpm)),
            ("Length", RangeLabel(cfg.MinLength, cfg.MaxLength, 0, Limits.MaxLength, "s")),
            ("Notes", RangeLabel(cfg.MinNotes, cfg.MaxNotes, 0, Limits.MaxNotes)),
            ("Min plays", cfg.MinPlays.ToString(CultureInfo.InvariantCulture)),
            ("Ranked", DateLabel(cfg.RankedAfter, cfg.RankedBefore)),
            ("NSFW", cfg.IncludeNsfw ? "include" : "exclude"),
        });

        return rows;
    }

    public static IReadOnlyList<(string Key, string Value)> SearchRows(
        int matched, int todo, AppConfig cfg)
    {
        var rows = new List<(string, string)>
        {
            ("Matching sets", matched.ToString(CultureInfo.InvariantCulture)),
            ("Already downloaded", Math.Max(0, matched - todo).ToString(CultureInfo.InvariantCulture)),
            ("To download", todo.ToString(CultureInfo.InvariantCulture)),
            ("Status", string.Join(", ", cfg.Statuses)),
            ("Keys", KeysLabel(cfg)),
        };

        if (cfg.Advanced && cfg.Query.Length > 0)
        {
            rows.Add(("Query", cfg.Query));
        }

        return rows;
    }

    /// <summary>Python's <c>format(value, "g")</c> for whole and decimal values.</summary>
    public static string FormatG(double value)
    {
        if (value == Math.Floor(value) && Math.Abs(value) < 1e15)
        {
            return ((long)value).ToString(CultureInfo.InvariantCulture);
        }

        return value.ToString("0.######", CultureInfo.InvariantCulture);
    }
}
