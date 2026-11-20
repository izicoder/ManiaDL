using System.Text.RegularExpressions;

namespace ManiaDL.Core.Parsing;

/// <summary>Port of util.simple_query_terms and its osu! operator regex.</summary>
public static class QueryText
{
    private static readonly Regex QueryOperator = new(
        @"\b(?:stars?|ar|cs|od|hp|dr|bpm|length|keys?|status|creator|artist|" +
        @"title|source|tag|favourites|ranked|updated|created|circles|sliders)" +
        @"\s*(?:>=|<=|>|<|=|:)",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    /// <summary>
    /// Terms to verify client-side for plain text queries. Queries using osu!
    /// operators are left to the API to avoid false negatives.
    /// </summary>
    public static List<string> SimpleQueryTerms(string? query)
    {
        var raw = (query ?? "").Trim();
        if (raw.Length == 0 || QueryOperator.IsMatch(raw))
        {
            return new List<string>();
        }

        return Regex.Split(raw, @"\s+")
            .Select(part => part.Trim('"').ToLowerInvariant())
            .Where(part => part.Length > 0)
            .ToList();
    }

    /// <summary>Strips quotes that would break the API parser; collapses whitespace.</summary>
    public static string QueryTextValue(string? value) =>
        string.Join(" ", (value ?? "").Replace("\"", " ").Split(
            (char[]?)null, StringSplitOptions.RemoveEmptyEntries));
}
