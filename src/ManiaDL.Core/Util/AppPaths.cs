using ManiaDL.Core.Constants;

namespace ManiaDL.Core.Util;

/// <summary>
/// Portable-first application paths. Config and default downloads live beside the
/// executable, never beside the assembly inside a <c>--onefile</c>-style bundle.
/// </summary>
public sealed class AppPaths
{
    public AppPaths(string baseDirectory)
    {
        BaseDirectory = Path.GetFullPath(baseDirectory);
    }

    public string BaseDirectory { get; }

    public string ConfigPath => Path.Combine(BaseDirectory, Limits.ConfigFileName);

    public string DefaultOut => Path.Combine(BaseDirectory, "downloads");

    /// <summary>Default base directory: the directory holding the executable.</summary>
    public static AppPaths Default => new(AppContext.BaseDirectory);
}
