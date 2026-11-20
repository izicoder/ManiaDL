using System.Text.RegularExpressions;

namespace ManiaDL.Core.Parsing;

/// <summary>Port of util.parse_date_range.</summary>
public static class DateRangeParser
{
    private static readonly Regex DateToken = new(
        @"^\d{4}(?:[-/.]\d{1,2}(?:[-/.]\d{1,2})?)?$",
        RegexOptions.CultureInvariant);

    private static readonly Regex Op = new(
        @"^\s*(?<op>>=|<=|>|<|=)\s*(?<v>\S+)\s*$",
        RegexOptions.CultureInvariant);

    private static readonly Regex Pair = new(
        @"^\s*(?<a>\S+?)\s*(?:\.\.|to)\s*(?<b>\S+)\s*$",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    private static readonly Regex YearPair = new(
        @"^\s*(?<a>\d{4})\s*-\s*(?<b>\d{4})\s*$",
        RegexOptions.CultureInvariant);

    public static (string? After, string? Before) Parse(string? text, string name = "date")
    {
        var raw = (text ?? "").Trim();
        if (raw.Length == 0 || raw.ToLowerInvariant() is "any" or "all" or "*")
        {
            return (null, null);
        }

        string? low = null;
        string? high = null;

        var pair = Pair.Match(raw);
        if (pair.Success)
        {
            low = pair.Groups["a"].Value;
            high = pair.Groups["b"].Value;
        }
        else
        {
            var yearPair = YearPair.Match(raw);
            if (yearPair.Success)
            {
                low = yearPair.Groups["a"].Value;
                high = yearPair.Groups["b"].Value;
            }
            else
            {
                var op = Op.Match(raw);
                if (op.Success)
                {
                    var value = op.Groups["v"].Value;
                    if (op.Groups["op"].Value.StartsWith('>'))
                    {
                        low = value;
                    }
                    else
                    {
                        // Known quirk, intentional parity: "=" and "<=" both map to an
                        // upper bound, not an exact date.
                        high = value;
                    }
                }
                else
                {
                    low = high = raw;
                }
            }
        }

        var after = low is null ? null : Normalise(low);
        var before = high is null ? null : Normalise(high);

        if (after is not null && before is not null &&
            string.CompareOrdinal(after, before) > 0)
        {
            throw new FormatException($"{name} range starts above it ends: '{raw}'");
        }

        return (after, before);
    }

    public static string Normalise(string token)
    {
        token = token.Trim().Replace('/', '-').Replace('.', '-');
        if (!DateToken.IsMatch(token))
        {
            throw new FormatException(
                $"Invalid date: '{token}' (use YYYY, YYYY-MM or YYYY-MM-DD)");
        }

        var parts = token.Split('-');
        if (parts.Length > 1)
        {
            parts[1] = parts[1].PadLeft(2, '0');
        }

        if (parts.Length > 2)
        {
            parts[2] = parts[2].PadLeft(2, '0');
        }

        return string.Join('-', parts);
    }
}
