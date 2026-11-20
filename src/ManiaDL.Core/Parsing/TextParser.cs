using System.Text.RegularExpressions;

namespace ManiaDL.Core.Parsing;

/// <summary>String helpers from util.py (as_text, as_bool, parse_csv, statuses, keys).</summary>
public static class TextParser
{
    public static string AsText(object? value) => value switch
    {
        null => "",
        string text => text,
        IEnumerable<string> items => string.Join(",", items),
        System.Collections.IEnumerable items => string.Join(
            ",",
            items.Cast<object?>().Select(item => Convert.ToString(item, System.Globalization.CultureInfo.InvariantCulture) ?? "")),
        bool flag => flag ? "True" : "False",
        IFormattable formattable => formattable.ToString(null, System.Globalization.CultureInfo.InvariantCulture),
        _ => value.ToString() ?? "",
    };

    public static bool AsBool(object? value)
    {
        if (value is bool flag)
        {
            return flag;
        }

        return AsText(value).Trim().ToLowerInvariant() is "1" or "true" or "yes" or "y" or "on";
    }

    /// <summary>Lowercase, comma/semicolon separated list. Spaces are kept inside terms.</summary>
    public static List<string> ParseCsv(object? value)
    {
        IEnumerable<string> parts;
        if (value is IEnumerable<string> list)
        {
            parts = list;
        }
        else if (value is System.Collections.IEnumerable enumerable and not string)
        {
            parts = enumerable.Cast<object?>()
                .Select(item => Convert.ToString(item, System.Globalization.CultureInfo.InvariantCulture) ?? "");
        }
        else
        {
            parts = Regex.Split(AsText(value ?? ""), "[,;]");
        }

        return parts
            .Select(part => part.Trim().ToLowerInvariant())
            .Where(part => part.Length > 0)
            .ToList();
    }

    public static List<string> ParseStatuses(string? text)
    {
        var parts = (text ?? "")
            .Split(',')
            .Select(part => part.Trim().ToLowerInvariant())
            .Where(part => part.Length > 0)
            .ToList();

        if (parts.Count == 0 || parts.Contains("any"))
        {
            return new List<string> { "any" };
        }

        var valid = new HashSet<string> { "graveyard", "ranked", "loved", "qualified", "pending" };
        var bad = parts.Where(part => !valid.Contains(part)).ToList();
        if (bad.Count > 0)
        {
            throw new FormatException($"Unknown status: {string.Join(", ", bad)}");
        }

        // Preserve order while removing duplicates.
        return parts.Distinct().ToList();
    }

    /// <summary>Returns null for "all"/blank, otherwise the sorted distinct key counts.</summary>
    public static IReadOnlyList<int>? ParseKeys(string? text)
    {
        var raw = (text ?? "").Trim().ToLowerInvariant();
        if (raw is "" or "all" or "any")
        {
            return null;
        }

        var keys = Regex.Split(raw, @"[,\s]+")
            .Where(item => item.Length > 0)
            .Select(item => int.Parse(item, System.Globalization.CultureInfo.InvariantCulture))
            .Distinct()
            .OrderBy(item => item)
            .ToList();

        if (keys.Any(key => key < 1 || key > 18))
        {
            throw new FormatException("Key counts must be between 1 and 18");
        }

        return keys;
    }
}
