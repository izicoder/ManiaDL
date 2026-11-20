using System.Net.Http.Headers;
using ManiaDL.Core.Constants;

namespace ManiaDL.Core.Util;

/// <summary>
/// Retry-After parsing. Uses <see cref="RetryConditionHeaderValue"/> (the BCL header
/// parser) instead of a hand-rolled HTTP-date parser, then clamps like util.retry_after.
/// </summary>
public static class RetryAfter
{
    public static int Parse(string? value, int fallback = 15, DateTimeOffset? now = null)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return fallback;
        }

        int seconds;
        if (RetryConditionHeaderValue.TryParse(value, out var parsed))
        {
            if (parsed.Delta is { } delta)
            {
                seconds = (int)delta.TotalSeconds;
            }
            else if (parsed.Date is { } date)
            {
                seconds = (int)(date - (now ?? DateTimeOffset.UtcNow)).TotalSeconds;
            }
            else
            {
                seconds = fallback;
            }
        }
        else
        {
            seconds = fallback;
        }

        return Math.Max(1, Math.Min(seconds, Limits.MaxRetryAfterSeconds));
    }
}
