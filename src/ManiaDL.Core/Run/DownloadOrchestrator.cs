using System.Net;
using ManiaDL.Core.Api;
using ManiaDL.Core.Config;
using ManiaDL.Core.Constants;
using ManiaDL.Core.Logging;
using ManiaDL.Core.Mirrors;
using ManiaDL.Core.State;
using ManiaDL.Core.Util;

namespace ManiaDL.Core.Run;

/// <summary>Port of app.py: auth -> search -> downloads, batch by batch.</summary>
public sealed class DownloadOrchestrator
{
    private readonly RunContext _ctx;
    private readonly Func<HttpMessageHandler> _handlerFactory;
    private readonly string _apiBase;
    private readonly string _tokenUrl;

    public DownloadOrchestrator(
        RunContext ctx,
        Func<HttpMessageHandler>? handlerFactory = null,
        string apiBase = ApiEndpoints.Api,
        string tokenUrl = ApiEndpoints.TokenUrl)
    {
        _ctx = ctx;
        _handlerFactory = handlerFactory ?? DefaultHandler;
        _apiBase = apiBase;
        _tokenUrl = tokenUrl;
    }

    private static HttpMessageHandler DefaultHandler() => new SocketsHttpHandler
    {
        ConnectTimeout = TimeSpan.FromSeconds(Limits.ConnectTimeoutSeconds),
        AutomaticDecompression = DecompressionMethods.All,
        AllowAutoRedirect = true,
        MaxConnectionsPerServer = Limits.HostConcurrency,
    };

    public async Task<RunResult> RunAsync(AppConfig cfg, string clientId, string secret)
    {
        var ct = _ctx.Token;
        _ctx.Progress.Reset();
        Directory.CreateDirectory(cfg.Out);

        foreach (var part in PathUtil.PartFiles(cfg.Out))
        {
            TryDelete(part);
        }

        TryDelete(Path.Combine(cfg.Out, Limits.FailedLinksFileName));

        var status = new StatusStore(cfg.Out, _ctx.Log, _ctx.Time).Load();

        using var handler = _handlerFactory();
        using var http = new HttpClient(handler, disposeHandler: false)
        {
            Timeout = Timeout.InfiniteTimeSpan,
        };
        var api = new OsuApiClient(http, _ctx.Time, _ctx.Log, _ctx.Rng, _apiBase, _tokenUrl);

        _ctx.Progress.SetMessage("Signing in to osu!...");
        var token = await api.GetTokenAsync(clientId, secret, ct).ConfigureAwait(false);

        var existing = FolderScanner.ScanExisting(cfg.Out);
        existing.UnionWith(status.Ids);
        status.PruneFailed(existing);
        if (status.Failed.Count > 0)
        {
            _ctx.Log.Info($"{status.Failed.Count} set(s) failed last run; they'll be retried.");
        }

        _ctx.Progress.SetMessage("Searching osu!...");
        var sets = await api.SearchSetsAsync(token, cfg, _ctx.Progress.SetMessage, ct)
            .ConfigureAwait(false);

        var todo = sets.Where(set => !existing.Contains(set.Id)).ToList();
        _ctx.Log.Info(
            $"Search finished: {sets.Count} matching, {sets.Count - todo.Count} already downloaded, " +
            $"{todo.Count} to fetch.");

        var failed = new Dictionary<long, string>();
        var elapsed = 0.0;

        if (todo.Count > 0 && !ct.IsCancellationRequested)
        {
            _ctx.Progress.SetMessage($"Downloading {todo.Count} sets...");
            (failed, elapsed) = await RunDownloadsAsync(http, cfg, todo, status).ConfigureAwait(false);
        }
        else if (todo.Count == 0)
        {
            _ctx.Progress.SetMessage("Nothing new to download.");
            _ctx.Log.Success("Nothing new to download.");
        }
        else
        {
            _ctx.Progress.SetMessage("Stopped.");
        }

        status.Flush();
        if (elapsed > 0)
        {
            _ctx.Progress.SetMessage(
                $"Done: {_ctx.Stats.Snapshot().Ok} downloaded, {_ctx.Stats.Snapshot().Fail} failed " +
                $"in {elapsed:0.0}s.");
        }

        return new RunResult
        {
            Matched = sets.Count,
            Existing = existing.Count,
            Todo = todo.Count,
            Failed = status.Failed.ToDictionary(id => id, id => status.Titles.GetValueOrDefault(id, "")),
            NewFailed = failed,
            Titles = status.Titles.ToDictionary(pair => pair.Key, pair => pair.Value),
            Elapsed = elapsed,
            Stopped = ct.IsCancellationRequested,
            MirrorsExhausted = _ctx.MirrorsExhausted,
        };
    }

    private async Task<(Dictionary<long, string> Failed, double Elapsed)> RunDownloadsAsync(
        HttpClient http,
        AppConfig cfg,
        IReadOnlyList<Beatmapset> todo,
        StatusStore status)
    {
        var overallTaskId = _ctx.Progress.AddTask("all", todo.Count);
        var started = _ctx.Time.GetUtcNow();
        var failed = new Dictionary<long, string>();
        var workers = new SemaphoreSlim(cfg.Workers);
        var service = new DownloadService(http, _ctx);

        try
        {
            for (var index = 0; index < todo.Count; index += cfg.Batch)
            {
                if (_ctx.Token.IsCancellationRequested)
                {
                    _ctx.Log.Info("Stopped by user.");
                    break;
                }

                if (_ctx.Disk.FreeGb(cfg.Out) < _ctx.MinFreeGb)
                {
                    _ctx.Log.Error("Low disk space, stopping.");
                    break;
                }

                var batch = todo.Skip(index).Take(cfg.Batch).ToList();
                _ctx.Log.Info($"Batch {index / cfg.Batch + 1}: {batch.Count} sets");

                try
                {
                    await Task.WhenAll(batch.Select(set =>
                        service.DownloadSetAsync(set, cfg, status, workers, overallTaskId, failed)))
                        .ConfigureAwait(false);
                }
                catch (OperationCanceledException) when (_ctx.Token.IsCancellationRequested)
                {
                    _ctx.Log.Info("Stopped by user.");
                    break;
                }

                status.Flush();
                if (_ctx.Token.IsCancellationRequested)
                {
                    _ctx.Log.Info("Stopped by user.");
                    break;
                }

                var pause = Math.Max(Limits.BatchPause, cfg.Workers * 0.5) + _ctx.Rng.NextDouble();
                await Task.Delay(TimeSpan.FromSeconds(pause), _ctx.Time, _ctx.Token)
                    .ConfigureAwait(false);

                if (_ctx.MirrorsExhausted)
                {
                    _ctx.Log.Error(
                        "Every mirror is rate-limiting us; stopping instead of hammering them. " +
                        "Re-run later.");
                    break;
                }
            }
        }
        finally
        {
            foreach (var leftover in PathUtil.PartFiles(cfg.Out))
            {
                TryDelete(leftover);
            }

            status.Flush();
            workers.Dispose();
        }

        return (failed, (_ctx.Time.GetUtcNow() - started).TotalSeconds);
    }

    private static void TryDelete(string path)
    {
        try
        {
            File.Delete(path);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // Leftovers are best-effort; a locked file is removed on the next run.
        }
    }
}
