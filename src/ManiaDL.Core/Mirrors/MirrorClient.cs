using System.Net;
using System.Net.Http.Headers;
using ManiaDL.Core.Constants;
using ManiaDL.Core.Run;
using ManiaDL.Core.Util;

namespace ManiaDL.Core.Mirrors;

/// <summary>Streams a set to <c>.part</c>, resuming with Range when the mirror supports it.</summary>
public sealed class MirrorClient
{
    private static readonly TimeSpan ReadTimeout = TimeSpan.FromSeconds(Limits.SockReadTimeoutSeconds);

    /// <summary>Fetches <paramref name="url"/> into <paramref name="partPath"/>.</summary>
    public async Task FetchAsync(
        HttpClient http,
        string url,
        string partPath,
        int taskId,
        RunContext ctx,
        CancellationToken ct)
    {
        var existing = 0L;
        try
        {
            if (File.Exists(partPath))
            {
                existing = new FileInfo(partPath).Length;
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            existing = 0;
        }

        using var request = new HttpRequestMessage(HttpMethod.Get, url);
        foreach (var header in ApiEndpoints.BrowserHeaders)
        {
            if (header.Key.Equals("User-Agent", StringComparison.OrdinalIgnoreCase))
            {
                request.Headers.TryAddWithoutValidation("User-Agent", header.Value);
            }
            else
            {
                request.Headers.TryAddWithoutValidation(header.Key, header.Value);
            }
        }

        request.Headers.TryAddWithoutValidation("Referer", MirrorTable.Referer(url));
        if (existing > 0)
        {
            request.Headers.Range = new RangeHeaderValue(existing, null);
        }

        var host = new Uri(url).Host;
        using var slot = await ctx.Hosts.For(host).AcquireAsync(ct).ConfigureAwait(false);

        using var response = await http
            .SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct)
            .ConfigureAwait(false);
        var status = (int)response.StatusCode;

        if (status == 429)
        {
            throw new RateLimitedException(
                RetryAfter.Parse(response.Headers.RetryAfter?.ToString(), 15, ctx.Time.GetUtcNow()));
        }

        if (status is 401 or 403 or 404 or 451)
        {
            throw new MirrorMissException($"HTTP {status}");
        }

        if (status == 416)
        {
            TryDelete(partPath);
            throw new HttpRequestException("range not satisfiable; restarting");
        }

        if (status is not (200 or 206))
        {
            throw new HttpRequestException($"HTTP {status}");
        }

        long start;
        long? total;
        FileMode mode;

        if (status == 206)
        {
            var range = response.Content.Headers.ContentRange;
            if (range?.From is null || range.From.Value != existing)
            {
                TryDelete(partPath);
                throw new HttpRequestException("bad Content-Range; restarting");
            }

            start = existing;
            total = range.Length;
            mode = FileMode.Append;
        }
        else
        {
            start = 0;
            total = response.Content.Headers.ContentLength;
            mode = FileMode.Create;
            if (existing > 0)
            {
                ctx.Log.Muted("mirror ignored Range; restarting this file");
            }
        }

        ctx.Progress.Update(taskId, completed: start, total: total);

        var received = start;
        var buffer = new byte[Limits.ChunkSize];
        await using var stream = await response.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
        await using (var handle = new FileStream(
                         partPath, mode, FileAccess.Write, FileShare.None, Limits.ChunkSize, useAsync: true))
        {
            while (true)
            {
                var read = await ReadChunkAsync(stream, buffer, ctx.Time, ct).ConfigureAwait(false);
                if (read == 0)
                {
                    break;
                }

                if (ct.IsCancellationRequested)
                {
                    throw new StoppedException();
                }

                await handle.WriteAsync(buffer.AsMemory(0, read), ct).ConfigureAwait(false);
                received += read;
                ctx.Stats.AddBytes(read);
                ctx.Progress.Update(taskId, advance: read);
            }
        }

        if (total is not null && received != total)
        {
            throw new PayloadException($"incomplete payload (got {received} of {total} bytes)");
        }

        if (received == 0)
        {
            throw new PayloadException("empty response body");
        }
    }

    private static async ValueTask<int> ReadChunkAsync(
        Stream stream,
        byte[] buffer,
        TimeProvider time,
        CancellationToken ct)
    {
        using var timeout = new CancellationTokenSource(ReadTimeout, time);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(ct, timeout.Token);
        try
        {
            return await stream.ReadAsync(buffer.AsMemory(), linked.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            throw new TimeoutException("read timed out");
        }
    }

    private static void TryDelete(string path)
    {
        try
        {
            File.Delete(path);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // Best effort; the next attempt truncates anyway.
        }
    }
}
