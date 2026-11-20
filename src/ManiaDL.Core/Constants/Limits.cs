namespace ManiaDL.Core.Constants;

/// <summary>Every tunable from constants.py, copied verbatim.</summary>
public static class Limits
{
    // Download behaviour
    public const int Retries = 6;
    public const int SearchRetries = 5;
    public const int SearchMaxPages = 1000;
    public const int FileTimeoutSeconds = 900;
    public const int SockReadTimeoutSeconds = 120;
    public const int ConnectTimeoutSeconds = 15;
    public const double MinFreeGb = 5.0;
    public const int ChunkSize = 128 * 1024;
    public const int MaxWorkers = 32;
    public const int MaxRetryAfterSeconds = 300;

    // Community mirror rate limiting (internal, always on)
    public const double HostInterval = 0.9;
    public const int HostConcurrency = 2;
    public const double HostJitterLow = 0.85;
    public const double HostJitterHigh = 1.15;

    // osu! API pacing: ~60 requests/minute at the base rate
    public const double SearchInterval = 1.05;
    public const double SearchMaxInterval = 30.0;
    public const double SearchJitter = 0.08;
    public const double BatchPause = 3.0;

    // Status persistence batching
    public const int SaveEvery = 8;
    public const double SaveIntervalSeconds = 5.0;
    public const double DiskCacheTtlSeconds = 3.0;

    // "No filter" sentinels used by the config and the query builder
    public const double MaxBpm = 9999.0;
    public const int MaxLength = 1_000_000_000;
    public const int MaxNotes = 1_000_000_000;

    // Status.json / config file names
    public const string StatusFileName = "status.json";
    public const int StatusVersion = 2;
    public const string LegacyIdsFileName = "downloaded_ids.txt";
    public const string LegacyFailedFileName = "failed.txt";
    public const string FailedLinksFileName = "failed_links.txt";
    public const string ConfigFileName = "mania_dl_config.json";

    // Log ring / display caps
    public const int LogRingSize = 500;
    public const int LogViewLimit = 3000;
}
