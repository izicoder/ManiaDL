using System.IO.Compression;
using System.Text;
using ManiaDL.Core.Api;
using ManiaDL.Core.Config;
using ManiaDL.Core.Constants;
using ManiaDL.Core.Util;

namespace ManiaDL.Core.Tests.Support;

/// <summary>Builders shared by the ported Python tests.</summary>
public static class TestData
{
    public static RawConfig LegacyRaw(string outDir, Action<RawConfig>? edit = null)
    {
        var raw = new RawConfig
        {
            Out = outDir,
            Statuses = "ranked",
            Keys = "4",
            MinSr = "4",
            MaxSr = "7",
            MinFavs = "10",
            Sort = "favourites_desc",
            Limit = "50",
            Workers = "4",
            Batch = "20",
        };
        edit?.Invoke(raw);
        return raw;
    }

    public static RawConfig AdvancedRaw(string outDir, Action<RawConfig>? edit = null)
    {
        var raw = LegacyRaw(outDir);
        raw.Advanced = true;
        raw.Query = "camellia";
        raw.Title = "ghost";
        raw.Artist = "";
        raw.Creator = "";
        raw.Source = "";
        raw.Exclude = "tv size";
        raw.Genre = "electronic";
        raw.Language = "instrumental";
        raw.BpmRange = "150-220";
        raw.LengthRange = "60-300";
        raw.NotesRange = "1000-5000";
        raw.MinPlays = "100";
        raw.RankedRange = "2020-01-01..2024-12-31";
        raw.IncludeNsfw = false;
        edit?.Invoke(raw);
        return raw;
    }

    public static RawConfig ApiRaw(string outDir, Action<RawConfig>? edit = null)
    {
        var raw = new RawConfig
        {
            Out = outDir,
            Statuses = "ranked",
            Keys = "all",
            MinSr = "0",
            MaxSr = "99",
            MinFavs = "0",
            Sort = "favourites_desc",
            Limit = "10",
            Workers = "1",
            Batch = "1",
        };
        edit?.Invoke(raw);
        return raw;
    }

    public static AppConfig Cfg(string outDir, Action<RawConfig>? edit = null) =>
        ConfigValidator.Build(ApiRaw(outDir, edit), new AppPaths(outDir));

    public static AppConfig AdvancedCfg(string outDir, Action<RawConfig>? edit = null) =>
        ConfigValidator.Build(AdvancedRaw(outDir, edit), new AppPaths(outDir));

    public static Beatmapset Set(
        long id = 1,
        string status = "ranked",
        double keys = 4,
        double stars = 5.0,
        string title = "Ghost",
        string artist = "Camellia",
        string creator = "Mapper",
        long favouriteCount = 100,
        long playCount = 500,
        double bpm = 180,
        long length = 200,
        long notes = 2000,
        string? rankedDate = "2023-05-01T00:00:00+00:00",
        string genre = "Electronic",
        string language = "Instrumental",
        bool nsfw = false,
        string tags = "electronic instrumental")
    {
        return new Beatmapset
        {
            Id = id,
            Title = title,
            TitleUnicode = title,
            Artist = artist,
            ArtistUnicode = artist,
            Creator = creator,
            Source = "Game",
            Tags = tags,
            Status = status,
            FavouriteCount = favouriteCount,
            PlayCount = playCount,
            Nsfw = nsfw,
            Bpm = bpm,
            GenreId = Lookups.GenreIds.GetValueOrDefault(genre.ToLowerInvariant()),
            LanguageId = Lookups.LanguageIds.GetValueOrDefault(language.ToLowerInvariant()),
            RankedDate = rankedDate,
            Beatmaps = new List<Beatmap>
            {
                new()
                {
                    ModeInt = 3,
                    Cs = keys,
                    DifficultyRating = stars,
                    CountCircles = notes,
                    CountSliders = 0,
                    CountSpinners = 0,
                    TotalLength = length,
                    Version = "Insane",
                },
            },
        };
    }

    /// <summary>A minimal valid .osz (zip with one .osu entry).</summary>
    public static byte[] MakeOsz(string beatmapName = "map.osu", string body = "osu file format v14")
    {
        using var buffer = new MemoryStream();
        using (var archive = new ZipArchive(buffer, ZipArchiveMode.Create, leaveOpen: true))
        {
            var entry = archive.CreateEntry(beatmapName);
            using var stream = entry.Open();
            var bytes = Encoding.UTF8.GetBytes(body);
            stream.Write(bytes, 0, bytes.Length);
        }

        return buffer.ToArray();
    }

    public static string WriteOsz(string folder, string fileName, string beatmapName = "map.osu")
    {
        var path = Path.Combine(folder, fileName);
        File.WriteAllBytes(path, MakeOsz(beatmapName));
        return path;
    }

    public static void WriteFile(string folder, string name, string contents) =>
        File.WriteAllText(Path.Combine(folder, name), contents, new UTF8Encoding(false));
}
