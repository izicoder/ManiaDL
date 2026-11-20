namespace ManiaDL.Core.Constants;

/// <summary>A community mirror endpoint. <c>{id}</c> is replaced with the set ID.</summary>
public sealed record Mirror(string Name, string Template, string Host);

public static class MirrorTable
{
    /// <summary>
    /// Keep the most reliable mirrors first; the scheduler also tracks health and
    /// rotates away from mirrors that fail or rate-limit.
    /// </summary>
    public static IReadOnlyList<Mirror> All { get; } = new[]
    {
        new Mirror("nerinyan", "https://api.nerinyan.moe/d/{id}", "api.nerinyan.moe"),
        new Mirror("nekoha", "https://mirror.nekoha.moe/api/download/{id}", "mirror.nekoha.moe"),
        new Mirror("catboy", "https://catboy.best/d/{id}n", "catboy.best"),
        new Mirror("beatconnect", "https://beatconnect.io/b/{id}/", "beatconnect.io"),
        new Mirror("osu.direct", "https://osu.direct/api/d/{id}", "osu.direct"),
        new Mirror("sayobot", "https://dl.sayobot.cn/beatmaps/download/full/{id}", "dl.sayobot.cn"),
        new Mirror("catboy-video", "https://catboy.best/d/{id}", "catboy.best"),
    };

    public static string Url(Mirror mirror, long id) =>
        mirror.Template.Replace("{id}", id.ToString());

    /// <summary>Scheme plus host, used for the mirror Referer header.</summary>
    public static string Referer(string url)
    {
        var index = url.IndexOf("://", StringComparison.Ordinal);
        var scheme = index >= 0 ? url[..index] : "https";
        var rest = index >= 0 ? url[(index + 3)..] : url;
        var slash = rest.IndexOf('/');
        var host = slash >= 0 ? rest[..slash] : rest;
        return $"{scheme}://{host}/";
    }
}
