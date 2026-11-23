using ManiaDL.Core.Constants;
using ManiaDL.Core.Parsing;
using ManiaDL.Core.Tests.Support;
using ManiaDL.Core.Util;
using Xunit;

namespace ManiaDL.Core.Tests;

// Ported 1:1 from tests/test_util.py.
public class RangeParserTests
{
    [Fact]
    public void Blank_means_no_filter()
    {
        Assert.Equal<(double? Low, double? High)>((null, null), RangeParser.ParseDouble(""));
        Assert.Equal<(double? Low, double? High)>((null, null), RangeParser.ParseDouble("any"));
    }

    [Fact]
    public void Pair_and_operators()
    {
        Assert.Equal<(double? Low, double? High)>((150.0, 220.0), RangeParser.ParseDouble("150-220"));
        Assert.Equal<(double? Low, double? High)>((150.0, 220.0), RangeParser.ParseDouble("150..220"));
        Assert.Equal<(double? Low, double? High)>((150.0, 220.0), RangeParser.ParseDouble("150 to 220"));
        Assert.Equal<(double? Low, double? High)>((150.0, null), RangeParser.ParseDouble(">=150"));
        Assert.Equal<(double? Low, double? High)>((null, 220.0), RangeParser.ParseDouble("<=220"));
        Assert.Equal<(double? Low, double? High)>((180.0, 180.0), RangeParser.ParseDouble("180"));
        Assert.Equal<(double? Low, double? High)>((180.0, 180.0), RangeParser.ParseDouble("=180"));
    }

    [Fact]
    public void Int_cast()
    {
        Assert.Equal<(int? Low, int? High)>((60, 300), RangeParser.ParseInt("60-300"));
    }

    [Fact]
    public void Invalid_and_inverted()
    {
        Assert.Throws<FormatException>(() => RangeParser.ParseDouble("nope"));
        Assert.Throws<FormatException>(() => RangeParser.ParseDouble("300-60"));
        Assert.Throws<FormatException>(() => RangeParser.ParseDouble("-1", "value", 0));
    }
}

public class DateRangeParserTests
{
    [Fact]
    public void Blank()
    {
        Assert.Equal<(string? After, string? Before)>((null, null), DateRangeParser.Parse(""));
    }

    [Fact]
    public void Ranges_and_normalisation()
    {
        Assert.Equal<(string? After, string? Before)>(
            ("2020-01", "2024-02"), DateRangeParser.Parse("2020-1..2024-2"));
        Assert.Equal<(string? After, string? Before)>(
            ("2020-01-02", "2020-12-31"), DateRangeParser.Parse("2020/01/02..2020/12/31"));
        Assert.Equal<(string? After, string? Before)>(
            ("2020", "2024"), DateRangeParser.Parse("2020..2024"));
        Assert.Equal<(string? After, string? Before)>(
            ("2020", null), DateRangeParser.Parse(">=2020"));
        Assert.Equal<(string? After, string? Before)>(
            (null, "2024"), DateRangeParser.Parse("<=2024"));
    }

    [Fact]
    public void Invalid()
    {
        Assert.Throws<FormatException>(() => DateRangeParser.Parse("not-a-date"));
        Assert.Throws<FormatException>(() => DateRangeParser.Parse("2024..2020"));
    }
}

public class ParseListsTests
{
    [Fact]
    public void Statuses()
    {
        Assert.Equal(new[] { "ranked", "loved" }, TextParser.ParseStatuses("ranked,loved"));
        Assert.Equal(new[] { "any" }, TextParser.ParseStatuses("any,ranked"));
        Assert.Equal(new[] { "ranked" }, TextParser.ParseStatuses("ranked,ranked"));
        Assert.Throws<FormatException>(() => TextParser.ParseStatuses("ranked,wat"));
    }

    [Fact]
    public void Keys()
    {
        Assert.Null(TextParser.ParseKeys("all"));
        Assert.Equal(new[] { 4, 7 }, TextParser.ParseKeys("4, 7 4"));
        Assert.Throws<FormatException>(() => TextParser.ParseKeys("0"));
        Assert.Throws<FormatException>(() => TextParser.ParseKeys("19"));
    }

    [Fact]
    public void Csv()
    {
        Assert.Equal(
            new[] { "anime", "video game", "rock" },
            TextParser.ParseCsv("Anime, Video Game;Rock"));
    }
}

public class QueryTermTests
{
    [Fact]
    public void Plain_text_is_client_filtered()
    {
        Assert.Equal(new[] { "camellia", "ghost" }, QueryText.SimpleQueryTerms("Camellia ghost"));
    }

    [Fact]
    public void Operator_queries_are_left_to_api()
    {
        Assert.Empty(QueryText.SimpleQueryTerms("stars>=5"));
        Assert.Empty(QueryText.SimpleQueryTerms("title=ghost"));
        Assert.Empty(QueryText.SimpleQueryTerms("keys:4"));
    }
}

public class MiscUtilTests
{
    [Fact]
    public void Direct_links_are_unique()
    {
        var links = Links.DirectLinks(123);
        var urls = links.Select(link => link.Url).ToList();
        Assert.Equal(urls.Count, urls.Distinct().Count());
        Assert.Equal("osu!", links[0].Name);
        Assert.Contains(links, link => link.Name == "catboy");
    }

    [Fact]
    public void Valid_osz()
    {
        using var tmp = new TempDir();
        var good = TestData.WriteOsz(tmp.Path, "good.osz");
        var bad = tmp.Combine("bad.osz");
        File.WriteAllText(bad, "<html>not a zip</html>");
        var noMap = tmp.Combine("no_map.osz");
        File.WriteAllBytes(noMap, TestData.MakeOsz("audio.mp3", "123"));

        Assert.True(OszValidator.IsValid(good));
        Assert.False(OszValidator.IsValid(bad));
        Assert.False(OszValidator.IsValid(noMap));
    }

    [Fact]
    public void Retry_after()
    {
        Assert.Equal(12, RetryAfter.Parse("12"));
        Assert.Equal(7, RetryAfter.Parse(null, 7));
        Assert.InRange(RetryAfter.Parse("9999"), 1, 300);
    }

    [Fact]
    public void Free_gb_returns_number()
    {
        using var tmp = new TempDir();
        var value = new DiskSpace(new ImmediateTimeProvider()).FreeGb(tmp.Path);
        Assert.True(value >= 0);
    }

    [Fact]
    public void Mirror_helpers()
    {
        Assert.Equal(
            "catboy.best",
            new Uri(MirrorTable.Url(MirrorTable.All.Single(m => m.Name == "catboy"), 1)).Host);
        Assert.Equal("https://catboy.best/", MirrorTable.Referer("https://catboy.best/d/1"));
    }
}
