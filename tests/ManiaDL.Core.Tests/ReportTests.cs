using ManiaDL.Core.Ui;
using Xunit;

namespace ManiaDL.Core.Tests;

// Ported 1:1 from tests/test_reports.py.
public class FailedEntriesTests
{
    [Fact]
    public void Entries_are_sorted_and_include_all_links()
    {
        var entries = FailedReport.FailedEntries(
            new long[] { 22, 11 },
            new Dictionary<long, string> { [22] = "Broken [map]", [11] = "Other" });

        Assert.Equal(new long[] { 11, 22 }, entries.Select(entry => entry.Id));

        var broken = entries[1];
        Assert.Equal("Broken [map]", broken.Title);
        var urls = broken.DirectLinks.Select(link => link.Url).ToList();
        Assert.Contains("https://osu.ppy.sh/beatmapsets/22", urls);
        Assert.Contains("https://catboy.best/d/22n", urls);
        Assert.Contains("https://api.nerinyan.moe/d/22", urls);
    }

    [Fact]
    public void Unknown_title()
    {
        var entries = FailedReport.FailedEntries(new long[] { 5 }, new Dictionary<long, string>());
        Assert.Equal("unknown title", entries[0].Title);
    }

    [Fact]
    public void Links_text_for_clipboard()
    {
        var entries = FailedReport.FailedEntries(
            new long[] { 22 }, new Dictionary<long, string> { [22] = "Broken" });
        var text = FailedReport.LinksText(entries);

        Assert.Contains("[22] Broken", text);
        Assert.Contains("https://osu.ppy.sh/beatmapsets/22", text);
        Assert.Contains("https://catboy.best/d/22n", text);
    }

    [Fact]
    public void No_failures()
    {
        Assert.Empty(FailedReport.FailedEntries(Array.Empty<long>(), new Dictionary<long, string>()));
    }
}
