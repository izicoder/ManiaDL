namespace ManiaDL.Core;

/// <summary>Authentication failed; user-facing and fatal for the run.</summary>
public sealed class AuthFatalException : Exception
{
    public AuthFatalException(string message, bool clearCredentials) : base(message)
    {
        ClearCredentials = clearCredentials;
    }

    /// <summary>True when saved credentials should be deleted (HTTP 400/401).</summary>
    public bool ClearCredentials { get; }
}

/// <summary>osu! returned HTTP 400 for the query; retry with fewer server filters.</summary>
public sealed class SearchRejectedException : Exception
{
    public SearchRejectedException(string message) : base(message)
    {
    }
}

/// <summary>A mirror refuses or lacks this set (HTTP 401/403/404/451).</summary>
public sealed class MirrorMissException : Exception
{
    public MirrorMissException(string message) : base(message)
    {
    }
}

/// <summary>HTTP 429: park the whole host instead of hammering it.</summary>
public sealed class RateLimitedException : Exception
{
    public RateLimitedException(int seconds) : base($"rate limited, retry after {seconds}s")
    {
        Seconds = seconds;
    }

    public int Seconds { get; }
}

/// <summary>The user pressed Stop; abandon this transfer without recording a failure.</summary>
public sealed class StoppedException : Exception
{
    public StoppedException() : base("stopped")
    {
    }
}

/// <summary>A truncated or empty payload; retried with a longer minimum backoff.</summary>
public sealed class PayloadException : Exception
{
    public PayloadException(string message) : base(message)
    {
    }
}

/// <summary>Fatal, user-facing run failure (search/auth).</summary>
public sealed class EngineFatalException : Exception
{
    public EngineFatalException(string message) : base(message)
    {
    }
}
