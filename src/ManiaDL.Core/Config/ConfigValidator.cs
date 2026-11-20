using System.Globalization;
using ManiaDL.Core.Constants;
using ManiaDL.Core.Parsing;
using ManiaDL.Core.Util;

namespace ManiaDL.Core.Config;

/// <summary>Port of config.cfg_from_raw: validates raw settings into an <see cref="AppConfig"/>.</summary>
public static class ConfigValidator
{
    public static AppConfig Build(RawConfig raw, AppPaths paths)
    {
        var outDir = PathUtil.ResolveOut(raw.Out, paths);

        var statuses = TextParser.ParseStatuses(raw.Statuses);
        var keys = TextParser.ParseKeys(raw.Keys);

        var minSr = ToFloat(raw.MinSr, 0.0);
        var maxSr = ToFloat(raw.MaxSr, 99.0);
        if (minSr < 0)
        {
            throw new ConfigException("Min star rating cannot be negative");
        }

        if (maxSr < minSr)
        {
            throw new ConfigException("Max star rating must be >= min star rating");
        }

        var minFavs = Math.Max(0, ToInt(raw.MinFavs, 0));
        var sort = Lookups.Sorts.Contains(raw.Sort) ? raw.Sort : Lookups.Sorts[0];
        var limit = Math.Max(1, ToInt(raw.Limit, 500));
        var workers = Math.Max(1, Math.Min(Limits.MaxWorkers, ToInt(raw.Workers, 4)));
        var batch = Math.Max(1, ToInt(raw.Batch, 20));
        var advanced = raw.Advanced;

        string query, title, artist, creator, source, rankedAfter = "", rankedBefore = "";
        List<string> exclude, genre, language;
        double minBpm, maxBpm;
        int minLength, maxLength, minNotes, maxNotes, minPlays;
        bool includeNsfw;

        if (advanced)
        {
            query = (raw.Query ?? "").Trim();
            title = (raw.Title ?? "").Trim();
            artist = (raw.Artist ?? "").Trim();
            creator = (raw.Creator ?? "").Trim();
            source = (raw.Source ?? "").Trim();
            exclude = TextParser.ParseCsv(raw.Exclude ?? "");
            genre = TextParser.ParseCsv(raw.Genre ?? "");
            language = TextParser.ParseCsv(raw.Language ?? "");
            minPlays = Math.Max(0, ToInt(raw.MinPlays, 0));
            includeNsfw = raw.IncludeNsfw;

            double? bpmLow, bpmHigh;
            try
            {
                (bpmLow, bpmHigh) = RangeParser.ParseDouble(
                    raw.BpmRange ?? "", "BPM", 0, 1000);
            }
            catch (FormatException ex)
            {
                throw new ConfigException(ex.Message);
            }

            minBpm = bpmLow ?? 0.0;
            maxBpm = bpmHigh ?? Limits.MaxBpm;

            int? lenLow, lenHigh;
            try
            {
                (lenLow, lenHigh) = RangeParser.ParseInt(
                    raw.LengthRange ?? "", "length", 0, 24 * 3600);
            }
            catch (FormatException ex)
            {
                throw new ConfigException(ex.Message);
            }

            minLength = lenLow ?? 0;
            maxLength = lenHigh ?? Limits.MaxLength;

            int? noteLow, noteHigh;
            try
            {
                (noteLow, noteHigh) = RangeParser.ParseInt(
                    raw.NotesRange ?? "", "note count", 0, 10_000_000);
            }
            catch (FormatException ex)
            {
                throw new ConfigException(ex.Message);
            }

            minNotes = noteLow ?? 0;
            maxNotes = noteHigh ?? Limits.MaxNotes;

            try
            {
                var (after, before) = DateRangeParser.Parse(raw.RankedRange ?? "", "ranked date");
                rankedAfter = after ?? "";
                rankedBefore = before ?? "";
            }
            catch (FormatException ex)
            {
                throw new ConfigException(ex.Message);
            }
        }
        else
        {
            query = "";
            title = "";
            artist = "";
            creator = "";
            source = "";
            exclude = new List<string>();
            genre = new List<string>();
            language = new List<string>();
            minBpm = 0.0;
            maxBpm = Limits.MaxBpm;
            minLength = 0;
            maxLength = Limits.MaxLength;
            minNotes = 0;
            maxNotes = Limits.MaxNotes;
            minPlays = 0;
            includeNsfw = false;
        }

        var genreIds = ResolveIds(genre, Lookups.GenreIds, "genre");
        var languageIds = ResolveIds(language, Lookups.LanguageIds, "language");
        var queryTerms = QueryText.SimpleQueryTerms(query);

        IReadOnlySet<string>? allowed = null;
        if (!statuses.Contains("any"))
        {
            var union = new HashSet<string>(StringComparer.Ordinal);
            foreach (var status in statuses)
            {
                union.UnionWith(Lookups.StatusSets[status]);
            }

            allowed = union;
        }

        return new AppConfig
        {
            Out = outDir,
            Statuses = statuses,
            Keys = keys,
            MinSr = minSr,
            MaxSr = maxSr,
            MinFavs = minFavs,
            Sort = sort,
            Limit = limit,
            Workers = workers,
            Batch = batch,
            Advanced = advanced,
            Query = query,
            Title = title,
            Artist = artist,
            Creator = creator,
            Source = source,
            Exclude = exclude,
            Genre = genre,
            Language = language,
            MinPlays = minPlays,
            IncludeNsfw = includeNsfw,
            MinBpm = minBpm,
            MaxBpm = maxBpm,
            MinLength = minLength,
            MaxLength = maxLength,
            MinNotes = minNotes,
            MaxNotes = maxNotes,
            RankedAfter = rankedAfter ?? "",
            RankedBefore = rankedBefore ?? "",
            GenreIds = genreIds,
            LanguageIds = languageIds,
            QueryTerms = queryTerms,
            AllowedStatuses = allowed,
        };
    }

    /// <summary>
    /// Turn partial genre/language names into the numeric ids the API expects.
    /// Unknown terms are a configuration error rather than a silently empty result.
    /// </summary>
    public static List<int> ResolveIds(
        IEnumerable<string> terms,
        IReadOnlyDictionary<string, int> mapping,
        string kind)
    {
        var ids = new HashSet<int>();
        var unknown = new List<string>();
        foreach (var term in terms)
        {
            var matches = mapping
                .Where(pair => pair.Key.Contains(term, StringComparison.Ordinal))
                .Select(pair => pair.Value)
                .ToList();
            if (matches.Count == 0)
            {
                unknown.Add(term);
                continue;
            }

            ids.UnionWith(matches);
        }

        if (unknown.Count > 0)
        {
            var known = string.Join(", ", mapping.Keys.OrderBy(name => name, StringComparer.Ordinal));
            throw new ConfigException(
                $"Unknown {kind}: {string.Join(", ", unknown)}. Try one of: {known}");
        }

        return ids.OrderBy(id => id).ToList();
    }

    private static int ToInt(string? value, int fallback) =>
        int.TryParse((value ?? "").Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out var parsed)
            ? parsed
            : fallback;

    private static double ToFloat(string? value, double fallback) =>
        double.TryParse((value ?? "").Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out var parsed)
            ? parsed
            : fallback;
}
