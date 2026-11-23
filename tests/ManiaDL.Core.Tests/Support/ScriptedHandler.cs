using System.Net;
using System.Text;

namespace ManiaDL.Core.Tests.Support;

public sealed record RecordedRequest(
    string Method,
    Uri Uri,
    IReadOnlyDictionary<string, string> Headers,
    string? Body)
{
    public string PathAndQuery => Uri.PathAndQuery;

    public string? Query(string key)
    {
        var query = Uri.Query.TrimStart('?');
        foreach (var part in query.Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            var pieces = part.Split('=', 2);
            if (Uri.UnescapeDataString(pieces[0]) == key)
            {
                return pieces.Length > 1 ? Uri.UnescapeDataString(pieces[1]) : "";
            }
        }

        return null;
    }
}

/// <summary>
/// A scripted <see cref="HttpMessageHandler"/>: each request pops the next
/// responder and every request is recorded for assertions.
/// </summary>
public sealed class ScriptedHandler : HttpMessageHandler
{
    private readonly Queue<Func<HttpRequestMessage, HttpResponseMessage>> _responses = new();
    private readonly List<RecordedRequest> _requests = new();

    public IReadOnlyList<RecordedRequest> Requests => _requests;

    public ScriptedHandler Enqueue(Func<HttpRequestMessage, HttpResponseMessage> responder)
    {
        _responses.Enqueue(responder);
        return this;
    }

    public ScriptedHandler Json(string json, int status = 200) =>
        Enqueue(_ => Responses.Json(json, status));

    public ScriptedHandler Status(int status, string text = "") =>
        Enqueue(_ => Responses.Text(text, status));

    public ScriptedHandler Body(byte[] body, int status = 200) =>
        Enqueue(_ => Responses.Body(body, status));

    public ScriptedHandler Missing() => Status(404);

    public ScriptedHandler RateLimited(int seconds) =>
        Enqueue(_ => Responses.WithHeader(429, "Retry-After", seconds.ToString()));

    public ScriptedHandler Incomplete(byte[] body, long contentLength) =>
        Enqueue(_ => Responses.Body(body, 200, contentLength));

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request, CancellationToken cancellationToken)
    {
        var body = request.Content is null
            ? null
            : await request.Content.ReadAsStringAsync(cancellationToken);
        var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var header in request.Headers)
        {
            headers[header.Key] = string.Join(",", header.Value);
        }

        _requests.Add(new RecordedRequest(
            request.Method.Method,
            request.RequestUri ?? new Uri("about:blank"),
            headers,
            body));

        if (_responses.Count == 0)
        {
            throw new InvalidOperationException(
                $"Unexpected request: {request.Method} {request.RequestUri}");
        }

        return _responses.Dequeue()(request);
    }
}

public static class Responses
{
    public static HttpResponseMessage Json(string json, int status = 200) =>
        new((HttpStatusCode)status)
        {
            Content = new StringContent(json, Encoding.UTF8, "application/json"),
        };

    public static HttpResponseMessage Text(string text, int status = 200) =>
        new((HttpStatusCode)status)
        {
            Content = new StringContent(text, Encoding.UTF8, "text/plain"),
        };

    public static HttpResponseMessage Body(byte[] body, int status = 200, long? contentLength = null)
    {
        var content = new ByteArrayContent(body);
        if (contentLength is not null)
        {
            content.Headers.ContentLength = contentLength;
        }

        return new HttpResponseMessage((HttpStatusCode)status) { Content = content };
    }

    public static HttpResponseMessage WithHeader(int status, string name, string value)
    {
        var response = new HttpResponseMessage((HttpStatusCode)status)
        {
            Content = new ByteArrayContent(Array.Empty<byte>()),
        };
        response.Headers.TryAddWithoutValidation(name, value);
        return response;
    }

    public static HttpResponseMessage Range(
        int status, long from, long to, long? length, byte[] body)
    {
        var content = new ByteArrayContent(body);
        content.Headers.ContentRange = length is null
            ? new System.Net.Http.Headers.ContentRangeHeaderValue(from, to)
            : new System.Net.Http.Headers.ContentRangeHeaderValue(from, to, length.Value);
        content.Headers.ContentLength = body.Length;
        return new HttpResponseMessage((HttpStatusCode)status) { Content = content };
    }
}
