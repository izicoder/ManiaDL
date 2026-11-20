using ManiaDL.Core.Constants;

namespace ManiaDL.Core.Util;

/// <summary>User-facing osu! and mirror links. No report files are ever written.</summary>
public static class Links
{
    public readonly record struct DirectLink(string Name, string Url);

    public static string OsuPage(long id) => $"https://osu.ppy.sh/beatmapsets/{id}";

    public static IReadOnlyList<DirectLink> DirectLinks(long id)
    {
        var links = new List<DirectLink> { new("osu!", OsuPage(id)) };
        var seen = new HashSet<string> { links[0].Url };
        foreach (var mirror in MirrorTable.All)
        {
            var url = MirrorTable.Url(mirror, id);
            if (seen.Add(url))
            {
                links.Add(new DirectLink(mirror.Name, url));
            }
        }

        return links;
    }
}
