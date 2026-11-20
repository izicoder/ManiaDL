using System.Globalization;
using System.Text.RegularExpressions;

namespace ManiaDL.Core.Parsing;

/// <summary>Port of util.parse_range: "150-220", "&gt;=150", "&lt;=220", "150" or blank.</summary>
public static class RangeParser
{
    private static readonly Regex Pair = new(
        @"^\s*(?<a>-?\d+(?:\.\d+)?)\s*(?:-|\.\.|to|,)\s*(?<b>-?\d+(?:\.\d+)?)\s*$",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    private static readonly Regex Op = new(
        @"^\s*(?<op>>=|<=|>|<|=)\s*(?<v>-?\d+(?:\.\d+)?)\s*$",
        RegexOptions.CultureInvariant);

    private static readonly Regex One = new(
        @"^\s*(?<v>-?\d+(?:\.\d+)?)\s*$",
        RegexOptions.CultureInvariant);

    public static (double? Low, double? High) ParseDouble(
        string? text,
        string name = "value",
        double? minimum = null,
        double? maximum = null)
    {
        var (low, high) = ParseRaw(text, name, minimum, maximum);
        return (low, high);
    }

    public static (int? Low, int? High) ParseInt(
        string? text,
        string name = "value",
        int? minimum = null,
        int? maximum = null)
    {
        var (low, high) = ParseRaw(text, name, minimum, maximum);
        // Python uses round() then int(), i.e. banker's rounding.
        return (
            low is null ? null : (int)Math.Round(low.Value, MidpointRounding.ToEven),
            high is null ? null : (int)Math.Round(high.Value, MidpointRounding.ToEven));
    }

    private static (double? Low, double? High) ParseRaw(
        string? text,
        string name,
        double? minimum,
        double? maximum)
    {
        var raw = (text ?? "").Trim();
        if (raw.Length == 0 || raw.ToLowerInvariant() is "any" or "all" or "*")
        {
            return (null, null);
        }

        double? low = null;
        double? high = null;

        var pair = Pair.Match(raw);
        if (pair.Success)
        {
            low = ParseNumber(pair.Groups["a"].Value);
            high = ParseNumber(pair.Groups["b"].Value);
        }
        else
        {
            var op = Op.Match(raw);
            if (op.Success)
            {
                var value = ParseNumber(op.Groups["v"].Value);
                var token = op.Groups["op"].Value;
                if (token is ">" or ">=")
                {
                    low = value;
                }
                else if (token is "<" or "<=")
                {
                    high = value;
                }
                else
                {
                    low = high = value;
                }
            }
            else
            {
                var one = One.Match(raw);
                if (!one.Success)
                {
                    throw new FormatException($"Invalid {name} range: '{raw}'");
                }

                low = high = ParseNumber(one.Groups["v"].Value);
            }
        }

        if (low is not null && high is not null && low > high)
        {
            throw new FormatException($"{name} range starts above it ends: '{raw}'");
        }

        if (minimum is not null && low is not null && low < minimum)
        {
            throw new FormatException($"{name} must be >= {Fmt(minimum.Value)}");
        }

        if (maximum is not null && high is not null && high > maximum)
        {
            throw new FormatException($"{name} must be <= {Fmt(maximum.Value)}");
        }

        return (low, high);
    }

    private static double ParseNumber(string value) =>
        double.Parse(value, NumberStyles.Float, CultureInfo.InvariantCulture);

    /// <summary>Python's <c>str.format(":g")</c> style formatting for whole numbers.</summary>
    private static string Fmt(double value) =>
        value == Math.Floor(value) && !double.IsInfinity(value)
            ? ((long)value).ToString(CultureInfo.InvariantCulture)
            : value.ToString("0.######", CultureInfo.InvariantCulture);
}
