using ManiaDL.Core.Config;

namespace ManiaDL.Core.Api;

/// <summary>
/// All user filters applied client-side, so API quirks cannot leak sets in.
/// This is authoritative; order and semantics are ported from api.qualifies.
/// </summary>
public static class Qualifier
{
    private static string TextField(Beatmapset set, string field) => field switch
    {
        "title" => $"{set.Title ?? ""} {set.TitleUnicode ?? ""}",
        "artist" => $"{set.Artist ?? ""} {set.ArtistUnicode ?? ""}",
        _ => field switch
        {
            "creator" => set.Creator ?? "",
            "source" => set.Source ?? "",
            _ => "",
        },
    };

    private static string Haystack(Beatmapset set)
    {
        var parts = new List<string>
        {
            TextField(set, "title"),
            TextField(set, "artist"),
            set.Creator ?? "",
            set.Source ?? "",
            set.Tags ?? "",
        };
        foreach (var beatmap in set.Beatmaps ?? new List<Beatmap>())
        {
            parts.Add(beatmap.Version ?? "");
        }

        return string.Join(" ", parts).ToLowerInvariant();
    }

    private static double SetBpm(Beatmapset set) => set.Bpm ?? 0.0;

    private static long SetLength(Beatmapset set)
    {
        var values = new List<long>();
        if (set.TotalLength is { } setLength)
        {
            values.Add(setLength);
        }

        foreach (var beatmap in set.Beatmaps ?? new List<Beatmap>())
        {
            if (beatmap.TotalLength is { } length)
            {
                values.Add(length);
            }
        }

        return values.Count == 0 ? 0 : values.Max();
    }

    private static long DiffLength(Beatmap beatmap, Beatmapset set) =>
        beatmap.TotalLength ?? SetLength(set);

    private static long Notes(Beatmap beatmap) =>
        (beatmap.CountCircles ?? 0) + (beatmap.CountSliders ?? 0) + (beatmap.CountSpinners ?? 0);

    private static string DatePrefix(string? value) =>
        string.IsNullOrEmpty(value) ? "" : value[..Math.Min(10, value.Length)];

    private static bool MatchesPrefix(string filter, string dateValue)
    {
        if (dateValue.Length == 0)
        {
            return false;
        }

        var prefix = dateValue.Length <= filter.Length ? dateValue : dateValue[..filter.Length];
        return string.CompareOrdinal(prefix, filter) >= 0;
    }

    private static bool BeforePrefix(string filter, string dateValue)
    {
        if (dateValue.Length == 0)
        {
            return false;
        }

        var prefix = dateValue.Length <= filter.Length ? dateValue : dateValue[..filter.Length];
        return string.CompareOrdinal(prefix, filter) <= 0;
    }

    public static bool Qualifies(Beatmapset set, AppConfig cfg)
    {
        if (!cfg.StatusAllowed(set.Status ?? ""))
        {
            return false;
        }

        if ((set.FavouriteCount ?? 0) < cfg.MinFavs)
        {
            return false;
        }

        if ((set.PlayCount ?? 0) < cfg.MinPlays)
        {
            return false;
        }

        if (!cfg.IncludeNsfw && set.Nsfw == true)
        {
            return false;
        }

        var textFields = new List<(string Needle, string Field)>();
        foreach (var field in new[] { "title", "artist", "creator", "source" })
        {
            var value = field switch
            {
                "title" => cfg.Title,
                "artist" => cfg.Artist,
                "creator" => cfg.Creator,
                _ => cfg.Source,
            };
            if (!string.IsNullOrEmpty(value))
            {
                textFields.Add((value.ToLowerInvariant(), field));
            }
        }

        if (cfg.QueryTerms.Count > 0 || cfg.Exclude.Count > 0 || textFields.Count > 0)
        {
            var haystack = Haystack(set);
            foreach (var term in cfg.QueryTerms)
            {
                if (!haystack.Contains(term, StringComparison.Ordinal))
                {
                    return false;
                }
            }

            foreach (var term in cfg.Exclude)
            {
                if (haystack.Contains(term, StringComparison.Ordinal))
                {
                    return false;
                }
            }
        }

        foreach (var (needle, field) in textFields)
        {
            if (!TextField(set, field).ToLowerInvariant().Contains(needle, StringComparison.Ordinal))
            {
                return false;
            }
        }

        if (cfg.GenreIds.Count > 0 && (set.GenreId is null || !cfg.GenreIds.Contains(set.GenreId.Value)))
        {
            return false;
        }

        if (cfg.LanguageIds.Count > 0 && (set.LanguageId is null || !cfg.LanguageIds.Contains(set.LanguageId.Value)))
        {
            return false;
        }

        var bpm = SetBpm(set);
        if (bpm < cfg.MinBpm || bpm > cfg.MaxBpm)
        {
            return false;
        }

        if (cfg.RankedAfter.Length > 0 &&
            !MatchesPrefix(cfg.RankedAfter, DatePrefix(set.RankedDate)))
        {
            return false;
        }

        if (cfg.RankedBefore.Length > 0 &&
            !BeforePrefix(cfg.RankedBefore, DatePrefix(set.RankedDate)))
        {
            return false;
        }

        foreach (var beatmap in set.Beatmaps ?? new List<Beatmap>())
        {
            if (beatmap.ModeInt != 3)
            {
                continue;
            }

            var keyCount = (int)Math.Truncate(beatmap.Cs ?? 0);
            if (cfg.Keys is not null && !cfg.Keys.Contains(keyCount))
            {
                continue;
            }

            var stars = beatmap.DifficultyRating ?? 0.0;
            if (!(cfg.MinSr <= stars && stars <= cfg.MaxSr))
            {
                continue;
            }

            var notes = Notes(beatmap);
            if (notes < cfg.MinNotes || notes > cfg.MaxNotes)
            {
                continue;
            }

            var length = DiffLength(beatmap, set);
            if (length < cfg.MinLength || length > cfg.MaxLength)
            {
                continue;
            }

            return true;
        }

        return false;
    }
}
