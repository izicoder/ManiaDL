using System.IO.Compression;

namespace ManiaDL.Core.Util;

/// <summary>Port of util.valid_osz: a real .osz is a zip with at least one .osu inside.</summary>
public static class OszValidator
{
    public static bool IsValid(string path)
    {
        try
        {
            var info = new FileInfo(path);
            if (!info.Exists || info.Length < 22)
            {
                return false;
            }

            using var archive = ZipFile.OpenRead(path);
            return archive.Entries.Any(entry =>
                entry.FullName.EndsWith(".osu", StringComparison.OrdinalIgnoreCase));
        }
        catch (Exception ex) when (ex is IOException or InvalidDataException or UnauthorizedAccessException or ArgumentException)
        {
            return false;
        }
    }
}
