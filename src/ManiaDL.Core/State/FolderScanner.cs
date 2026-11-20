using System.Globalization;
using System.Text.RegularExpressions;

namespace ManiaDL.Core.State;

/// <summary>Port of state.scan_existing: beatmapset IDs already present as NNN*.osz.</summary>
public static class FolderScanner
{
    private static readonly Regex Prefix = new(@"^(\d+)(?:[ .]|$)", RegexOptions.CultureInvariant);

    public static HashSet<long> ScanExisting(string folder)
    {
        var found = new HashSet<long>();
        if (!Directory.Exists(folder))
        {
            return found;
        }

        foreach (var path in Directory.EnumerateFileSystemEntries(folder))
        {
            var name = Path.GetFileName(path);
            var match = Prefix.Match(name);
            if (!match.Success)
            {
                continue;
            }

            if (string.Equals(Path.GetExtension(name), ".osz", StringComparison.OrdinalIgnoreCase) &&
                long.TryParse(match.Groups[1].Value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var id))
            {
                found.Add(id);
            }
        }

        return found;
    }
}
