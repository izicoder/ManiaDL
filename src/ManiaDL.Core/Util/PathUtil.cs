using ManiaDL.Core.Constants;

namespace ManiaDL.Core.Util;

public static class PathUtil
{
    /// <summary>Python's <c>Path.expanduser()</c> for the forms a user actually types.</summary>
    public static string ExpandUser(string path)
    {
        if (string.IsNullOrEmpty(path))
        {
            return path;
        }

        if (path == "~" || path.StartsWith("~/", StringComparison.Ordinal) ||
            path.StartsWith("~\\", StringComparison.Ordinal))
        {
            var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            var rest = path.Length <= 2 ? "" : path[2..];
            return rest.Length == 0 ? home : Path.Combine(home, rest);
        }

        return path;
    }

    public static string DefaultOut(AppPaths paths) => paths.DefaultOut;

    public static string ResolveOut(string? value, AppPaths paths)
    {
        var text = string.IsNullOrWhiteSpace(value) ? paths.DefaultOut : value;
        return PathUtil.ExpandUser(text);
    }

    /// <summary>Folder contract: only .osz files plus exactly one status.json.</summary>
    public static IEnumerable<string> PartFiles(string folder) =>
        Directory.Exists(folder)
            ? Directory.EnumerateFiles(folder, "*.part", SearchOption.TopDirectoryOnly)
            : Array.Empty<string>();

    public static string StatusPath(string folder) =>
        Path.Combine(folder, Limits.StatusFileName);
}
