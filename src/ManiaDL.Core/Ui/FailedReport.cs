using System.Globalization;
using ManiaDL.Core.Util;

namespace ManiaDL.Core.Ui;

public sealed record FailedEntry(long Id, string Title, IReadOnlyList<Links.DirectLink> DirectLinks);

/// <summary>
/// Port of reports.py: failed-download rows and clipboard text. Nothing is written
/// to the download folder; failures live in the UI.
/// </summary>
public static class FailedReport
{
    public static IReadOnlyList<FailedEntry> FailedEntries(
        IEnumerable<long> failedIds,
        IReadOnlyDictionary<long, string> titles)
    {
        var ids = failedIds.Distinct().OrderBy(id => id);
        return ids.Select(id =>
        {
            var title = titles.TryGetValue(id, out var value) && !string.IsNullOrWhiteSpace(value)
                ? value
                : "unknown title";
            return new FailedEntry(id, title, Links.DirectLinks(id));
        }).ToList();
    }

    public static string LinksText(IReadOnlyList<FailedEntry> entries)
    {
        var lines = new List<string> { "ManiaDL failed downloads", "" };
        foreach (var entry in entries)
        {
            lines.Add($"[{entry.Id.ToString(CultureInfo.InvariantCulture)}] {entry.Title}");
            foreach (var link in entry.DirectLinks)
            {
                lines.Add($"  {link.Name,-12} {link.Url}");
            }

            lines.Add("");
        }

        return string.Join("\n", lines);
    }
}
