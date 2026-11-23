using System.Text.Json;
using ManiaDL.Core.Config;
using ManiaDL.Core.Tests.Support;
using ManiaDL.Core.Util;
using Xunit;

namespace ManiaDL.Core.Tests;

// Ported 1:1 from tests/test_config.py.
public class CfgFromRawTests
{
    [Fact]
    public void Old_config_gets_defaults()
    {
        using var tmp = new TempDir();
        var cfg = ConfigValidator.Build(
            TestData.LegacyRaw(tmp.Combine("out")), new AppPaths(tmp.Path));

        Assert.False(cfg.Advanced);
        Assert.Equal("", cfg.Query);
        Assert.Empty(cfg.Exclude);
        Assert.Equal(0.0, cfg.MinBpm);
        Assert.Equal(9999.0, cfg.MaxBpm);
        Assert.Equal(0, cfg.MinNotes);
        Assert.Equal(1_000_000_000, cfg.MaxNotes);
    }

    [Fact]
    public void Advanced_config()
    {
        using var tmp = new TempDir();
        var cfg = ConfigValidator.Build(
            TestData.AdvancedRaw(tmp.Combine("out")), new AppPaths(tmp.Path));

        Assert.True(cfg.Advanced);
        Assert.Equal("camellia", cfg.Query);
        Assert.Equal(new[] { "tv size" }, cfg.Exclude);
        Assert.Equal(new[] { "electronic" }, cfg.Genre);
        Assert.Equal(new[] { 10 }, cfg.GenreIds);
        Assert.Equal(new[] { 5 }, cfg.LanguageIds);
        Assert.Equal(new[] { "camellia" }, cfg.QueryTerms);
        Assert.Equal(150.0, cfg.MinBpm);
        Assert.Equal(220.0, cfg.MaxBpm);
        Assert.Equal(60, cfg.MinLength);
        Assert.Equal(300, cfg.MaxLength);
        Assert.Equal(1000, cfg.MinNotes);
        Assert.Equal(5000, cfg.MaxNotes);
        Assert.Equal("2020-01-01", cfg.RankedAfter);
        Assert.Equal("2024-12-31", cfg.RankedBefore);
    }

    [Fact]
    public void Validation()
    {
        using var tmp = new TempDir();
        var paths = new AppPaths(tmp.Path);
        var outDir = tmp.Combine("out");

        Assert.Throws<ConfigException>(() => ConfigValidator.Build(
            TestData.LegacyRaw(outDir, raw =>
            {
                raw.MinSr = "8";
                raw.MaxSr = "4";
            }), paths));
        Assert.Throws<ConfigException>(() => ConfigValidator.Build(
            TestData.LegacyRaw(outDir, raw => raw.MinSr = "-1"), paths));
        Assert.Throws<ConfigException>(() => ConfigValidator.Build(
            TestData.AdvancedRaw(outDir, raw => raw.BpmRange = "300-100"), paths));
        Assert.Throws<ConfigException>(() => ConfigValidator.Build(
            TestData.AdvancedRaw(outDir, raw => raw.Genre = "drum and bass"), paths));
    }

    [Fact]
    public void Partial_genre_names_resolve()
    {
        using var tmp = new TempDir();
        var cfg = ConfigValidator.Build(
            TestData.AdvancedRaw(tmp.Combine("out"), raw => raw.Genre = "elec"),
            new AppPaths(tmp.Path));

        Assert.Equal(new[] { 10 }, cfg.GenreIds);
    }

    [Fact]
    public void Limits_and_clamps()
    {
        using var tmp = new TempDir();
        var cfg = ConfigValidator.Build(
            TestData.LegacyRaw(tmp.Combine("out"), raw =>
            {
                raw.Workers = "999";
                raw.Batch = "0";
                raw.Limit = "0";
                raw.MinFavs = "-5";
            }),
            new AppPaths(tmp.Path));

        Assert.Equal(32, cfg.Workers);
        Assert.Equal(1, cfg.Batch);
        Assert.Equal(1, cfg.Limit);
        Assert.Equal(0, cfg.MinFavs);
    }
}

public class MigrationTests
{
    [Fact]
    public void Migrate_fills_new_keys_only()
    {
        using var tmp = new TempDir();
        var paths = new AppPaths(tmp.Path);
        var store = new ConfigStore(paths);
        File.WriteAllText(store.Path, """
            {
              "client_id": "1",
              "client_secret": "secret",
              "workers": 9,
              "safe_mode": false,
              "slide_window": true
            }
            """);

        var (migrated, changed) = store.LoadAndMigrate();

        Assert.True(changed);
        Assert.Equal("9", migrated.Workers);
        Assert.False(migrated.Extra?.ContainsKey("safe_mode") ?? false);
        Assert.False(migrated.Extra?.ContainsKey("slide_window") ?? false);
        Assert.False(migrated.Advanced);
        Assert.Equal("", migrated.Query);
    }

    [Fact]
    public void Migrate_is_idempotent()
    {
        using var tmp = new TempDir();
        var store = new ConfigStore(new AppPaths(tmp.Path));
        var (saved, _) = store.LoadAndMigrate();
        Assert.True(store.Save(saved));

        var (_, changed) = store.LoadAndMigrate();
        Assert.False(changed);
    }

    [Fact]
    public void Save_preserves_unknown_keys_and_uses_python_names()
    {
        using var tmp = new TempDir();
        var paths = new AppPaths(tmp.Path);
        var store = new ConfigStore(paths);
        File.WriteAllText(store.Path, """
            { "client_id": "1", "future_key": { "nested": true }, "min_sr": 4 }
            """);

        var config = store.Load();
        Assert.True(store.Save(config));

        using var document = JsonDocument.Parse(File.ReadAllText(store.Path));
        var root = document.RootElement;
        Assert.Equal("1", root.GetProperty("client_id").GetString());
        Assert.True(root.GetProperty("future_key").GetProperty("nested").GetBoolean());
        Assert.Equal("4", root.GetProperty("min_sr").GetString());
        Assert.True(root.TryGetProperty("bpm_range", out _));
        Assert.False(root.TryGetProperty("safe_mode", out _));
    }
}

public class StatusAllowedTests
{
    [Fact]
    public void Any_allows_everything()
    {
        using var tmp = new TempDir();
        var cfg = ConfigValidator.Build(
            TestData.LegacyRaw(tmp.Combine("out"), raw => raw.Statuses = "any"),
            new AppPaths(tmp.Path));

        Assert.True(cfg.StatusAllowed("graveyard"));
    }

    [Fact]
    public void Ranked_includes_approved()
    {
        using var tmp = new TempDir();
        var cfg = ConfigValidator.Build(
            TestData.LegacyRaw(tmp.Combine("out"), raw => raw.Statuses = "ranked"),
            new AppPaths(tmp.Path));

        Assert.True(cfg.StatusAllowed("ranked"));
        Assert.True(cfg.StatusAllowed("approved"));
        Assert.False(cfg.StatusAllowed("loved"));
    }
}
