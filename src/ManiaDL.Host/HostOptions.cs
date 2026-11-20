namespace ManiaDL.Host;

/// <summary>Command-line flags. Debug-only flags are honoured in Debug builds.</summary>
public sealed class HostOptions
{
    public int? DebugPort { get; private init; }
    public string? FakeScenario { get; private init; }
    public string? DataDir { get; private init; }
    public string? DevUrl { get; private init; }
    public string? ApiBase { get; private init; }

    public static HostOptions Parse(string[] args)
    {
        int? debugPort = null;
        string? fake = null;
        string? dataDir = null;
        string? devUrl = null;
        string? apiBase = null;

        for (var index = 0; index < args.Length; index++)
        {
            var arg = args[index];
            string? Next() => index + 1 < args.Length ? args[++index] : null;

            switch (arg)
            {
                case "--debug-port":
                    if (int.TryParse(Next(), out var port))
                    {
                        debugPort = port;
                    }

                    break;
                case "--fake-engine":
                    fake = Next();
                    break;
                case "--data-dir":
                    dataDir = Next();
                    break;
                case "--dev-url":
                    devUrl = Next();
                    break;
#if DEBUG
                case "--api-base":
                    apiBase = Next();
                    break;
#endif
            }
        }

        return new HostOptions
        {
            DebugPort = debugPort,
            FakeScenario = fake,
            DataDir = dataDir,
            DevUrl = devUrl,
            ApiBase = apiBase,
        };
    }
}
