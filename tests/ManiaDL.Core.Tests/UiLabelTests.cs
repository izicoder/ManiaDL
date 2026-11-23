using ManiaDL.Core.Config;
using ManiaDL.Core.Constants;
using ManiaDL.Core.Tests.Support;
using ManiaDL.Core.Ui;
using ManiaDL.Core.Util;
using Xunit;

namespace ManiaDL.Core.Tests;

// Ported 1:1 from tests/test_ui.py.
public class LabelTests
{
    private static AppConfig MakeCfg(Action<RawConfig>? edit = null)
    {
        using var tmp = new TempDir();
        var raw = TestData.AdvancedRaw(tmp.Combine("out"), r =>
        {
            r.Artist = "camellia";
            r.Creator = "mapper";
            r.Source = "game";
            edit?.Invoke(r);
        });
        return ConfigValidator.Build(raw, new AppPaths(tmp.Path));
    }

    [Fact]
    public void Range_labels()
    {
        Assert.Equal("any", UiLabels.RangeLabel(0, 9999, 0, 9999));
        Assert.Equal("150-220", UiLabels.RangeLabel(150, 220, 0, 9999));
        Assert.Equal(">=150", UiLabels.RangeLabel(150, 9999, 0, 9999));
        Assert.Equal("<=220", UiLabels.RangeLabel(0, 220, 0, 9999));
        Assert.Equal("60-300s", UiLabels.RangeLabel(60, 300, 0, 1_000_000_000, "s"));
    }

    [Fact]
    public void Date_labels()
    {
        Assert.Equal("any", UiLabels.DateLabel("", ""));
        Assert.Equal("2020..2024", UiLabels.DateLabel("2020", "2024"));
        Assert.Equal(">=2020", UiLabels.DateLabel("2020", ""));
        Assert.Equal("<=2024", UiLabels.DateLabel("", "2024"));
    }

    [Fact]
    public void Keys_label()
    {
        Assert.Equal("all", UiLabels.KeysLabel(MakeCfg(r => r.Keys = "all")));
        Assert.Equal("4K, 7K", UiLabels.KeysLabel(MakeCfg(r => r.Keys = "4,7")));
    }
}

public class SummaryTests
{
    private static AppConfig MakeCfg(Action<RawConfig>? edit = null)
    {
        using var tmp = new TempDir();
        var raw = TestData.AdvancedRaw(tmp.Combine("out"), r =>
        {
            r.Artist = "camellia";
            r.Creator = "mapper";
            r.Source = "game";
            edit?.Invoke(r);
        });
        return ConfigValidator.Build(raw, new AppPaths(tmp.Path));
    }

    [Fact]
    public void Basic_rows_only_when_advanced_off()
    {
        var rows = UiLabels.SummaryRows(MakeCfg(r => r.Advanced = false))
            .ToDictionary(row => row.Key, row => row.Value);

        Assert.Equal("ranked", rows["Status"]);
        Assert.Equal("Most favourites", rows["Sort"]);
        Assert.Equal("4 / 20", rows["Parallel / batch"]);
        Assert.DoesNotContain("Title contains", rows.Keys);
    }

    [Fact]
    public void Advanced_rows()
    {
        var rows = UiLabels.SummaryRows(MakeCfg())
            .ToDictionary(row => row.Key, row => row.Value);

        Assert.Equal("ghost", rows["Title contains"]);
        Assert.Equal("electronic", rows["Genre"]);
        Assert.Equal("150-220", rows["BPM"]);
        Assert.Equal("60-300s", rows["Length"]);
        Assert.Equal("1000-5000", rows["Notes"]);
        Assert.Equal("2020-01-01..2024-12-31", rows["Ranked"]);
        Assert.Equal("exclude", rows["NSFW"]);
    }

    [Fact]
    public void Search_rows()
    {
        var rows = UiLabels.SearchRows(10, 7, MakeCfg())
            .ToDictionary(row => row.Key, row => row.Value);

        Assert.Equal("10", rows["Matching sets"]);
        Assert.Equal("3", rows["Already downloaded"]);
        Assert.Equal("7", rows["To download"]);
        Assert.Equal("camellia", rows["Query"]);
    }
}
