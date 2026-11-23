using ManiaDL.Core.Api;
using ManiaDL.Core.Config;
using ManiaDL.Core.Tests.Support;
using ManiaDL.Core.Util;
using Xunit;

namespace ManiaDL.Core.Tests;

// Ported from tests/test_api.py (query building half).
public class BuildQueryTests
{
    [Fact]
    public void Legacy_defaults_do_not_add_filters()
    {
        using var tmp = new TempDir();
        var cfg = TestData.Cfg(tmp.Combine("out"));

        Assert.Equal("", QueryBuilder.Build(cfg, null));
        Assert.Equal("", QueryBuilder.Minimal(cfg, null));
    }

    [Fact]
    public void Advanced_query()
    {
        using var tmp = new TempDir();
        var cfg = TestData.AdvancedCfg(tmp.Combine("out"), raw =>
        {
            raw.Artist = "camellia";
            raw.Creator = "mapper";
            raw.Source = "game";
        });

        var query = QueryBuilder.Build(cfg, 4);
        foreach (var part in new[]
                 {
                     "camellia", "ghost", "mapper", "game", "keys=4", "stars>=4",
                     "stars<=7", "favourites>=10", "bpm>=150", "bpm<=220",
                     "length>=60", "length<=300", "ranked>=2020-01-01",
                     "ranked<=2024-12-31",
                 })
        {
            Assert.Contains(part, query);
        }
    }

    [Fact]
    public void Minimal_query()
    {
        using var tmp = new TempDir();
        var cfg = TestData.AdvancedCfg(tmp.Combine("out"), raw => raw.Title = "ghost");

        Assert.Equal("camellia keys=7", QueryBuilder.Minimal(cfg, 7));
    }

    [Fact]
    public void Search_params_narrows_genre_and_language()
    {
        using var tmp = new TempDir();
        var cfg = TestData.AdvancedCfg(tmp.Combine("out"));

        var parameters = QueryBuilder.SearchParams(cfg, 4);
        Assert.Equal("10", parameters["g"]);
        Assert.Equal("5", parameters["l"]);
        Assert.Contains("keys=4", parameters["q"]);
    }

    [Fact]
    public void Search_params_keeps_multiple_genres_client_side()
    {
        using var tmp = new TempDir();
        var cfg = TestData.AdvancedCfg(tmp.Combine("out"), raw => raw.Genre = "electronic, rock");

        var parameters = QueryBuilder.SearchParams(cfg, null);
        Assert.False(parameters.ContainsKey("g"));
        Assert.Equal(new[] { 4, 10 }, cfg.GenreIds);
    }
}

// Ported from tests/test_api.py (QualifiesTests).
public class QualifierTests
{
    private static AppConfig Cfg(Action<RawConfig>? edit = null)
    {
        using var tmp = new TempDir();
        return ConfigValidator.Build(
            TestData.ApiRaw(tmp.Combine("out"), edit), new AppPaths(tmp.Path));
    }

    [Fact]
    public void Basic_match()
    {
        var cfg = Cfg(raw =>
        {
            raw.Keys = "4";
            raw.MinSr = "4";
            raw.MaxSr = "7";
            raw.MinFavs = "10";
        });

        Assert.True(Qualifier.Qualifies(TestData.Set(), cfg));
    }

    [Fact]
    public void Status_and_favourites()
    {
        var cfg = Cfg(raw => raw.MinFavs = "10");

        Assert.True(Qualifier.Qualifies(TestData.Set(status: "approved"), cfg));
        Assert.False(Qualifier.Qualifies(TestData.Set(status: "loved"), cfg));
        Assert.False(Qualifier.Qualifies(TestData.Set(favouriteCount: 0), cfg));
    }

    [Fact]
    public void Keys_and_stars()
    {
        var cfg = Cfg(raw =>
        {
            raw.Keys = "7";
            raw.MinSr = "4";
            raw.MaxSr = "7";
        });

        Assert.False(Qualifier.Qualifies(TestData.Set(keys: 4), cfg));
        Assert.True(Qualifier.Qualifies(TestData.Set(keys: 7), cfg));
        Assert.False(Qualifier.Qualifies(TestData.Set(stars: 9), cfg));
    }

    [Fact]
    public void Text_filters()
    {
        var cfg = Cfg(raw =>
        {
            raw.Advanced = true;
            raw.Title = "ghost";
            raw.Artist = "camellia";
            raw.Creator = "mapper";
        });

        Assert.True(Qualifier.Qualifies(TestData.Set(), cfg));
        Assert.False(Qualifier.Qualifies(TestData.Set(title: "Other"), cfg));
        Assert.False(Qualifier.Qualifies(TestData.Set(artist: "Other"), cfg));
        Assert.False(Qualifier.Qualifies(TestData.Set(creator: "Other"), cfg));
    }

    [Fact]
    public void Free_query_and_exclude()
    {
        var cfg = Cfg(raw =>
        {
            raw.Advanced = true;
            raw.Query = "camellia ghost";
            raw.Exclude = "tv size";
        });

        Assert.True(Qualifier.Qualifies(TestData.Set(), cfg));
        Assert.False(Qualifier.Qualifies(TestData.Set(artist: "Other"), cfg));
        Assert.False(Qualifier.Qualifies(
            TestData.Set(tags: "electronic instrumental tv size"), cfg));
    }

    [Fact]
    public void Genre_language_bpm_length_notes_plays_dates()
    {
        var cfg = Cfg(raw =>
        {
            raw.Advanced = true;
            raw.Genre = "electronic";
            raw.Language = "instrumental";
            raw.BpmRange = "150-220";
            raw.LengthRange = "60-300";
            raw.NotesRange = "1000-5000";
            raw.MinPlays = "100";
            raw.RankedRange = "2020-01-01..2024-12-31";
        });

        Assert.True(Qualifier.Qualifies(TestData.Set(), cfg));
        Assert.False(Qualifier.Qualifies(TestData.Set(genre: "Rock"), cfg));
        Assert.False(Qualifier.Qualifies(TestData.Set(language: "English"), cfg));
        Assert.False(Qualifier.Qualifies(TestData.Set(bpm: 300), cfg));
        Assert.False(Qualifier.Qualifies(TestData.Set(length: 30), cfg));
        Assert.False(Qualifier.Qualifies(TestData.Set(notes: 100), cfg));
        Assert.False(Qualifier.Qualifies(TestData.Set(playCount: 0), cfg));
        Assert.False(Qualifier.Qualifies(TestData.Set(rankedDate: null), cfg));
    }

    [Fact]
    public void Length_applies_to_matching_diff()
    {
        var cfg = Cfg(raw =>
        {
            raw.Advanced = true;
            raw.LengthRange = "60-300";
        });

        var data = TestData.Set();
        data.Beatmaps![0] = data.Beatmaps[0] with { TotalLength = 30 };
        data.Beatmaps.Add(new Beatmap
        {
            ModeInt = 3,
            Cs = 4,
            DifficultyRating = 5.0,
            CountCircles = 2000,
            CountSliders = 0,
            CountSpinners = 0,
            TotalLength = 500,
            Version = "Another",
        });

        Assert.False(Qualifier.Qualifies(data, cfg));

        data.Beatmaps[0] = data.Beatmaps[0] with { TotalLength = 200 };
        Assert.True(Qualifier.Qualifies(data, cfg));
    }

    [Fact]
    public void Nsfw_filter()
    {
        Assert.False(Qualifier.Qualifies(TestData.Set(nsfw: true), Cfg()));

        var cfg = Cfg(raw =>
        {
            raw.Advanced = true;
            raw.IncludeNsfw = true;
        });
        Assert.True(Qualifier.Qualifies(TestData.Set(nsfw: true), cfg));
    }

    [Fact]
    public void Genre_and_language_use_api_ids()
    {
        var cfg = Cfg(raw =>
        {
            raw.Advanced = true;
            raw.Genre = "electronic";
            raw.Language = "instrumental";
        });

        Assert.True(Qualifier.Qualifies(TestData.Set(), cfg));

        var data = TestData.Set(genre: "Rock");
        Assert.False(Qualifier.Qualifies(data, cfg));
    }

    [Fact]
    public void Unknown_genre_is_rejected_at_parse_time()
    {
        Assert.Throws<ConfigException>(() => Cfg(raw =>
        {
            raw.Advanced = true;
            raw.Genre = "drum and bass";
        }));
    }
}
