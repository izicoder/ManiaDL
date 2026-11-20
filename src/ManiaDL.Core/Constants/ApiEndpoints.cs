namespace ManiaDL.Core.Constants;

/// <summary>osu! API endpoints and user agents. Copied verbatim from constants.py.</summary>
public static class ApiEndpoints
{
    public const string Api = "https://osu.ppy.sh/api/v2";
    public const string TokenUrl = "https://osu.ppy.sh/oauth/token";
    public const string ApiUserAgent = "osu-mania-downloader/2.0";

    /// <summary>Mirror downloads need a browser UA or Cloudflare answers 403.</summary>
    public const string BrowserUserAgent =
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

    /// <summary>Headers for mirror downloads only. Never send these to the osu! API.</summary>
    public static IReadOnlyDictionary<string, string> BrowserHeaders { get; } =
        new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["User-Agent"] = BrowserUserAgent,
            ["Accept"] = "*/*",
            ["Accept-Language"] = "en-US,en;q=0.9",
            ["Cache-Control"] = "no-cache",
        };

    /// <summary>The "how to get keys" text logged on an authentication failure.</summary>
    public const string KeyGuide =
        """
        How to get your osu! API keys
        1. Log in at https://osu.ppy.sh.
        2. Open your settings: https://osu.ppy.sh/home/account/edit
        3. Scroll to the OAuth section and click New OAuth Application.
        4. Name it anything (e.g. "mania dl"). Callback URL: http://localhost
        5. Click Register. You now see your Client ID (a number) and Client Secret
           (a long string). Copy both. If you lose the secret, you can reset it on
           the same page.
        6. Keep the secret private. Never share it or post it publicly.
        """;
}
