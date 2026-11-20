using System.Globalization;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using ManiaDL.Core.Config;
using ManiaDL.Core.Constants;
using ManiaDL.Core.Logging;
using ManiaDL.Core.Util;

namespace ManiaDL.Core.Api;

/// <summary>OAuth, cursor-paginated search, pacing and the 400 fallback chain.</summary>
public sealed class OsuApiClient
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        NumberHandling = JsonNumberHandling.AllowReadingFromString,
    };

    private readonly HttpClient _http;
    private readonly TimeProvider _time;
    private readonly RunLog _log;
    private readonly Random _rng;
    private readonly string _apiBase;
    private readonly string _tokenUrl;

    public OsuApiClient(
        HttpClient http,
        TimeProvider time,
        RunLog log,
        Random rng,
        string apiBase = ApiEndpoints.Api,
        string tokenUrl = ApiEndpoints.TokenUrl)
    {
        _http = http;
        _time = time;
        _log = log;
        _rng = rng;
        _apiBase = apiBase.TrimEnd('/');
        _tokenUrl = tokenUrl;
    }

    public async Task<string> GetTokenAsync(string clientId, string secret, CancellationToken ct)
    {
        if (!int.TryParse(clientId, NumberStyles.Integer, CultureInfo.InvariantCulture, out var id))
        {
            throw new AuthFatalException("osu! client ID must be a number.", clearCredentials: false);
        }

        var payload = new
        {
            client_id = id,
            client_secret = secret,
            grant_type = "client_credentials",
            scope = "public",
        };

        var lastError = "";
        for (var attempt = 0; attempt < 3; attempt++)
        {
            using var response = await _http.PostAsJsonAsync(_tokenUrl, payload, JsonOptions, ct)
                .ConfigureAwait(false);
            var status = (int)response.StatusCode;

            if (status == 200)
            {
                using var document = JsonDocument.Parse(
                    await response.Content.ReadAsStringAsync(ct).ConfigureAwait(false));
                if (!document.RootElement.TryGetProperty("access_token", out var token) ||
                    token.ValueKind != JsonValueKind.String ||
                    string.IsNullOrEmpty(token.GetString()))
                {
                    throw new AuthFatalException("osu! returned no access token.", clearCredentials: false);
                }

                return token.GetString()!;
            }

            var detail = Truncate(await response.Content.ReadAsStringAsync(ct).ConfigureAwait(false), 200);
            lastError = detail;

            if (status is 400 or 401)
            {
                throw new AuthFatalException(
                    $"Auth failed (HTTP {status}). {detail}".TrimEnd(), clearCredentials: true);
            }

            if (status == 429 || status >= 500)
            {
                var wait = RetryAfter.Parse(response.Headers.RetryAfter?.ToString(), 15, _time.GetUtcNow());
                _log.Warning(
                    $"osu! token endpoint returned HTTP {status}; waiting {wait}s before retry {attempt + 1}/3.");
                await Task.Delay(TimeSpan.FromSeconds(wait), _time, ct).ConfigureAwait(false);
                continue;
            }

            _log.Warning(
                $"osu! refused the token request (HTTP {status}). That's their server, not your keys; " +
                "saved credentials were kept. Try again in a minute.");
            throw new AuthFatalException(
                $"Auth failed (HTTP {status}). {detail}".TrimEnd(), clearCredentials: false);
        }

        throw new AuthFatalException($"Auth failed after retries. {lastError}".TrimEnd(),
            clearCredentials: false);
    }

    public async Task<IReadOnlyList<Beatmapset>> SearchSetsAsync(
        string token,
        AppConfig cfg,
        Action<string>? status,
        CancellationToken ct)
    {
        _authorization = token;
        var found = new Dictionary<long, Beatmapset>();
        var order = new List<long>();
        var pacer = new SearchPacer(_time, _rng);
        var keys = cfg.Keys is null
            ? new int?[] { null }
            : cfg.Keys.Select(key => (int?)key).ToArray();

        var combos = new List<(string ApiStatus, int? Key)>();
        var seenCombos = new HashSet<(string, int?)>();
        foreach (var userStatus in cfg.Statuses)
        {
            var apiStatuses = userStatus == "any"
                ? new[] { "any" }
                : Lookups.ApiStatuses[userStatus].ToArray();
            foreach (var apiStatus in apiStatuses)
            {
                foreach (var key in keys)
                {
                    if (seenCombos.Add((apiStatus, key)))
                    {
                        combos.Add((apiStatus, key));
                    }
                }
            }
        }

        foreach (var (apiStatus, key) in combos)
        {
            ct.ThrowIfCancellationRequested();
            if (found.Count >= cfg.Limit)
            {
                break;
            }

            var parameters = QueryBuilder.SearchParams(cfg, key);
            if (apiStatus != "any")
            {
                parameters["s"] = apiStatus;
            }

            try
            {
                await SearchOneAsync(parameters, cfg, found, order, status, pacer, ct).ConfigureAwait(false);
            }
            catch (SearchRejectedException ex)
            {
                _log.Warning(
                    $"osu! rejected the advanced query ({ex.Message}); retrying with fewer server-side filters.");
                var fallback = new Dictionary<string, string>(parameters, StringComparer.Ordinal);
                var fallbackQuery = QueryBuilder.Minimal(cfg, key);
                if (fallbackQuery.Length > 0 &&
                    (!parameters.TryGetValue("q", out var current) || fallbackQuery != current))
                {
                    fallback["q"] = fallbackQuery;
                }
                else
                {
                    fallback.Remove("q");
                }

                try
                {
                    await SearchOneAsync(fallback, cfg, found, order, status, pacer, ct).ConfigureAwait(false);
                }
                catch (SearchRejectedException)
                {
                    fallback.Remove("q");
                    _log.Warning(
                        "still rejected; searching without the text query. Client-side filters still apply.");
                    await SearchOneAsync(fallback, cfg, found, order, status, pacer, ct).ConfigureAwait(false);
                }
            }
        }

        var sets = order.Select(id => found[id]).ToList();
        _log.Info($"Search: {sets.Count} matching sets from {pacer.Requests} osu! requests.");
        return sets.Take(cfg.Limit).ToList();
    }

    private async Task SearchOneAsync(
        Dictionary<string, string> parameters,
        AppConfig cfg,
        Dictionary<long, Beatmapset> found,
        List<long> order,
        Action<string>? status,
        SearchPacer pacer,
        CancellationToken ct)
    {
        string? cursor = null;
        var seenCursors = new HashSet<string>(StringComparer.Ordinal);
        var pages = 0;
        var scanned = 0;

        while (found.Count < cfg.Limit)
        {
            if (ct.IsCancellationRequested)
            {
                return;
            }

            var query = new Dictionary<string, string>(parameters, StringComparer.Ordinal);
            if (!string.IsNullOrEmpty(cursor))
            {
                query["cursor_string"] = cursor;
            }

            JsonDocument? data = null;
            for (var attempt = 0; attempt < Limits.SearchRetries; attempt++)
            {
                await pacer.WaitAsync(ct).ConfigureAwait(false);
                try
                {
                    using var response = await SendSearchAsync(query, ct).ConfigureAwait(false);
                    var code = (int)response.StatusCode;

                    if (code == 429)
                    {
                        var wait = RetryAfter.Parse(
                            response.Headers.RetryAfter?.ToString(), 15, _time.GetUtcNow());
                        // The pacer makes the retry itself wait; no inline sleep that
                        // would stack on top of the normal spacing.
                        pacer.Penalise(wait);
                        _log.Warning($"… osu! API rate limit; waiting {wait}s");
                        continue;
                    }

                    if (code >= 500)
                    {
                        var wait = Math.Min(Math.Pow(2, attempt) + _rng.NextDouble() * 1.5, 30);
                        pacer.Penalise(wait);
                        _log.Warning($"! osu! API HTTP {code}; retrying in {wait:0}s");
                        continue;
                    }

                    if (code == 400)
                    {
                        var detail = Truncate(
                            await response.Content.ReadAsStringAsync(ct).ConfigureAwait(false), 200);
                        throw new SearchRejectedException(detail.Length > 0 ? detail : "HTTP 400");
                    }

                    if (code != 200)
                    {
                        throw new EngineFatalException($"Search failed (HTTP {code}).");
                    }

                    var body = await response.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
                    data = JsonDocument.Parse(body);
                    pacer.Success();
                    break;
                }
                catch (SearchRejectedException)
                {
                    throw;
                }
                catch (Exception ex) when (
                    ex is HttpRequestException or TaskCanceledException or JsonException)
                {
                    if (ct.IsCancellationRequested)
                    {
                        throw;
                    }

                    var wait = Math.Min(Math.Pow(2, attempt) + _rng.NextDouble() * 1.5, 30);
                    pacer.Penalise(wait);
                    _log.Warning($"! search error ({ex.GetType().Name}); retrying in {wait:0}s");
                }
            }

            if (data is null)
            {
                throw new EngineFatalException("Search failed after retries.");
            }

            using (data)
            {
                var root = data.RootElement;
                if (root.TryGetProperty("error", out var error) && error.ValueKind is not JsonValueKind.Null)
                {
                    _log.Warning($"! osu! search: {error}");
                }

                var pageSets = ReadBeatmapsets(root);
                scanned += pageSets.Count;
                foreach (var set in pageSets)
                {
                    if (set.Id <= 0)
                    {
                        continue;
                    }

                    if (!Qualifier.Qualifies(set, cfg))
                    {
                        continue;
                    }

                    if (!found.ContainsKey(set.Id))
                    {
                        order.Add(set.Id);
                    }

                    found[set.Id] = set;
                }

                var matched = Math.Min(found.Count, cfg.Limit);
                status?.Invoke($"Searching... {matched} / {cfg.Limit} matching ({scanned} scanned)");

                cursor = root.TryGetProperty("cursor_string", out var cursorElement) &&
                         cursorElement.ValueKind == JsonValueKind.String
                    ? cursorElement.GetString()
                    : null;

                if (string.IsNullOrEmpty(cursor) || pageSets.Count == 0)
                {
                    break;
                }

                if (!seenCursors.Add(cursor))
                {
                    break;
                }

                pages++;
                if (pages >= Limits.SearchMaxPages)
                {
                    _log.Warning("! search page cap reached; stopping search.");
                    break;
                }
            }
        }
    }

    private async Task<HttpResponseMessage> SendSearchAsync(
        Dictionary<string, string> query,
        CancellationToken ct)
    {
        var builder = new StringBuilder(_apiBase);
        builder.Append("/beatmapsets/search?");
        builder.Append(string.Join("&", query.Select(pair =>
            $"{Uri.EscapeDataString(pair.Key)}={Uri.EscapeDataString(pair.Value)}")));

        using var request = new HttpRequestMessage(HttpMethod.Get, builder.ToString());
        request.Headers.TryAddWithoutValidation("User-Agent", ApiEndpoints.ApiUserAgent);
        if (_authorization is not null)
        {
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _authorization);
        }

        return await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct)
            .ConfigureAwait(false);
    }

    private string? _authorization;

    private static List<Beatmapset> ReadBeatmapsets(JsonElement root)
    {
        if (!root.TryGetProperty("beatmapsets", out var sets) || sets.ValueKind != JsonValueKind.Array)
        {
            return new List<Beatmapset>();
        }

        try
        {
            return sets.Deserialize<List<Beatmapset>>(JsonOptions) ?? new List<Beatmapset>();
        }
        catch (JsonException)
        {
            return new List<Beatmapset>();
        }
    }

    private static string Truncate(string text, int length)
    {
        var trimmed = text.Trim();
        return trimmed.Length <= length ? trimmed : trimmed[..length].Trim();
    }
}
