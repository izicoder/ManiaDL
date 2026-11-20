using ManiaDL.Core.Api;
using ManiaDL.Core.Config;
using ManiaDL.Core.Constants;
using ManiaDL.Core.Run;
using ManiaDL.Core.State;
using ManiaDL.Core.Util;

namespace ManiaDL.Core.Mirrors;

/// <summary>Port of mirrors.download_set: retries, mirror fallback, resume and validation.</summary>
public sealed class DownloadService
{
    private readonly HttpClient _http;
    private readonly RunContext _ctx;
    private readonly MirrorClient _client = new();

    public DownloadService(HttpClient http, RunContext ctx)
    {
        _http = http;
        _ctx = ctx;
    }

    public async Task DownloadSetAsync(
        Beatmapset set,
        AppConfig cfg,
        StatusStore status,
        SemaphoreSlim workers,
        int overallTaskId,
        IDictionary<long, string> failed)
    {
        var sid = set.Id;
        var title = set.Title ?? "";
        var dest = Path.Combine(cfg.Out, $"{sid}.osz");
        var part = Path.ChangeExtension(dest, ".part");

        await workers.WaitAsync(_ctx.Token).ConfigureAwait(false);
        var taskId = _ctx.Progress.AddTask($"{sid} {Truncate(title, 38)}", total: null);
        _ctx.Stats.AddActive(1);
        var tried = new HashSet<string>(StringComparer.Ordinal);
        try
        {
            if (File.Exists(dest) && OszValidator.IsValid(dest))
            {
                _ctx.Log.Muted($"{sid} already on disk");
                status.NoteSuccess(sid);
                return;
            }

            for (var attempt = 0; attempt < Limits.Retries; attempt++)
            {
                if (_ctx.Token.IsCancellationRequested)
                {
                    _ctx.Log.Info($"Stopping before {sid}.");
                    break;
                }

                if (_ctx.Disk.FreeGb(cfg.Out) < Limits.MinFreeGb)
                {
                    _ctx.Log.Error("Low disk space, stopping this set.");
                    break;
                }

                var (mirror, wait) = new MirrorScheduler(_ctx).Choose(tried);
                if (mirror is null)
                {
                    if (wait > TimeSpan.Zero)
                    {
                        _ctx.MirrorsExhausted = true;
                        _ctx.Log.Warning("… all mirrors are cooling down; stopping this set");
                    }
                    else
                    {
                        _ctx.Log.Warning($"! {sid}: no untried mirror left");
                    }

                    break;
                }

                var url = Constants.MirrorTable.Url(mirror, sid);
                try
                {
                    await FetchWithTimeoutAsync(url, part, taskId).ConfigureAwait(false);

                    if (!OszValidator.IsValid(part))
                    {
                        TryDelete(part);
                        throw new FormatException("not a valid .osz");
                    }

                    File.Move(part, dest, overwrite: true);
                    status.NoteSuccess(sid);
                    _ctx.Mirrors.State(mirror.Name).MarkOk();
                    _ctx.Stats.AddOk();
                    _ctx.Log.Success($"+ {sid} via {mirror.Name}");
                    return;
                }
                catch (RateLimitedException ex)
                {
                    var until = _ctx.Mirrors.ParkHost(
                        mirror.Host, Constants.MirrorTable.All, ex.Seconds, _ctx.Time.GetUtcNow(), out var park);
                    _ctx.Log.Warning(
                        $"… {mirror.Host} cooling down for {(int)park.TotalSeconds}s");
                    _ = until;
                    ResetProgress(part, taskId);
                }
                catch (StoppedException)
                {
                    _ctx.Log.Info($"Stopped {sid}.");
                    return;
                }
                catch (OperationCanceledException) when (_ctx.Token.IsCancellationRequested)
                {
                    _ctx.Log.Info($"Stopped {sid}.");
                    return;
                }
                catch (MirrorMissException ex)
                {
                    tried.Add(mirror.Name);
                    _ctx.Mirrors.State(mirror.Name).MarkMiss();
                    ResetProgress(part, taskId);
                    _ctx.Log.Warning($"! {sid} {mirror.Name}: {ex.Message} (try {attempt + 1}/{Limits.Retries})");
                }
                catch (Exception ex) when (
                    ex is TimeoutException or HttpRequestException or FormatException or
                        IOException or UnauthorizedAccessException or PayloadException or InvalidDataException)
                {
                    _ctx.Mirrors.State(mirror.Name).MarkMiss();
                    ResetProgress(part, taskId);
                    var isPayload = ex is PayloadException;
                    _ctx.Log.Warning(
                        $"! {sid} {mirror.Name}: {ex.GetType().Name} {ex.Message} " +
                        $"(try {attempt + 1}/{Limits.Retries})");

                    if (ex is IOException && _ctx.Disk.FreeGb(cfg.Out) < Limits.MinFreeGb)
                    {
                        _ctx.Log.Error("Low disk space, stopping this set.");
                        break;
                    }

                    var delay = Math.Min(Math.Pow(2, attempt) + _ctx.Rng.NextDouble() * 1.5, 45);
                    delay *= 1.25;
                    if (isPayload)
                    {
                        delay = Math.Max(delay, 10);
                    }

                    await Task.Delay(TimeSpan.FromSeconds(delay), _ctx.Time, _ctx.Token)
                        .ConfigureAwait(false);
                }
            }

            if (_ctx.Token.IsCancellationRequested)
            {
                // Leave the set untouched; it stays in the queue for next run.
                return;
            }

            _ctx.Stats.AddFail();
            failed[sid] = title;
            status.NoteFailure(sid, title);
            _ctx.Log.Error($"x {sid} gave up after {Limits.Retries} tries");
            _ctx.Log.Info($"→ download manually: {Links.OsuPage(sid)}");
        }
        finally
        {
            _ctx.Stats.AddActive(-1);
            _ctx.Progress.RemoveTask(taskId);
            _ctx.Progress.Update(overallTaskId, advance: 1);
            workers.Release();
        }
    }

    private async Task FetchWithTimeoutAsync(string url, string part, int taskId)
    {
        using var fileTimeout = new CancellationTokenSource(
            TimeSpan.FromSeconds(Limits.FileTimeoutSeconds), _ctx.Time);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(
            _ctx.Token, fileTimeout.Token);
        try
        {
            await _client.FetchAsync(_http, url, part, taskId, _ctx, linked.Token)
                .ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (!_ctx.Token.IsCancellationRequested)
        {
            throw new TimeoutException("file transfer timed out");
        }
    }

    private void ResetProgress(string part, int taskId)
    {
        var size = 0L;
        try
        {
            if (File.Exists(part))
            {
                size = new FileInfo(part).Length;
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            size = 0;
        }

        _ctx.Progress.Update(taskId, completed: size);
    }

    private static void TryDelete(string path)
    {
        try
        {
            File.Delete(path);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // Best effort.
        }
    }

    private static string Truncate(string text, int length) =>
        text.Length <= length ? text : text[..length];
}
