using System.Globalization;
using System.Threading.Channels;
using ManiaDL.Core.Config;
using ManiaDL.Core.Logging;
using ManiaDL.Core.Run;
using ManiaDL.Core.Ui;
using ManiaDL.Core.Util;

namespace ManiaDL.Core.Engine;

/// <summary>
/// Deterministic engine used by the agent e2e harness (--fake-engine). It validates
/// settings exactly like the real engine, then plays a scripted scenario.
/// </summary>
public sealed class FakeEngine : IEngine
{
    private readonly AppPaths _paths;
    private readonly ConfigStore _store;
    private readonly string _scenario;
    private readonly Channel<EngineEvent> _events =
        Channel.CreateUnbounded<EngineEvent>(new UnboundedChannelOptions { SingleReader = true });

    private readonly object _lock = new();
    private CancellationTokenSource? _stop;
    private volatile EngineState _state = EngineState.Idle;
    private AppConfig? _cfg;

    public FakeEngine(AppPaths paths, ConfigStore store, string scenario)
    {
        _paths = paths;
        _store = store;
        _scenario = scenario;
    }

    public EngineState State => _state;

    public ChannelReader<EngineEvent> Events => _events.Reader;

    public Task<StartOutcome> StartAsync(RawConfig raw)
    {
        AppConfig cfg;
        CancellationTokenSource stop;
        lock (_lock)
        {
            if (_state != EngineState.Idle)
            {
                return Task.FromResult(StartOutcome.Fail("A run is already active."));
            }

            try
            {
                cfg = ConfigValidator.Build(raw, _paths);
            }
            catch (ConfigException ex)
            {
                return Task.FromResult(StartOutcome.Fail(ex.Message));
            }

            var clientId = (raw.ClientId ?? "").Trim();
            var secret = (raw.ClientSecret ?? "").Trim();
            if (clientId.Length == 0 || secret.Length == 0)
            {
                return Task.FromResult(StartOutcome.Fail(
                    "Enter your osu! client ID and secret.", "client_id"));
            }

            if (!clientId.All(char.IsAsciiDigit))
            {
                return Task.FromResult(StartOutcome.Fail(
                    "The osu! client ID must be a number.", "client_id"));
            }

            raw.ClientId = clientId;
            raw.ClientSecret = secret;
            _store.Save(raw, log: null);

            _cfg = cfg;
            _stop = new CancellationTokenSource();
            stop = _stop;
            _state = EngineState.Running;
        }

        Emit(new StateChangedEvent("running"));
        _ = PlayAsync(cfg, stop.Token);
        return Task.FromResult(StartOutcome.Ok());
    }

    public void Stop()
    {
        lock (_lock)
        {
            if (_state != EngineState.Running)
            {
                return;
            }

            _state = EngineState.Stopping;
            _stop?.Cancel();
        }

        Emit(new StateChangedEvent("stopping"));
    }

    private async Task PlayAsync(AppConfig cfg, CancellationToken ct)
    {
        try
        {
            EmitLog(LogLevel.Info, $"Fake engine scenario: {_scenario}.");
            await Task.Delay(120, ct).ConfigureAwait(false);

            switch (_scenario)
            {
                case "auth-error":
                    await PlayAuthErrorAsync(ct).ConfigureAwait(false);
                    break;
                case "failures":
                    await PlayFailuresAsync(cfg, ct).ConfigureAwait(false);
                    break;
                case "mirrors-exhausted":
                    await PlayMirrorsExhaustedAsync(cfg, ct).ConfigureAwait(false);
                    break;
                case "slow":
                    await PlaySlowAsync(cfg, ct).ConfigureAwait(false);
                    break;
                default:
                    await PlaySuccessAsync(cfg, ct).ConfigureAwait(false);
                    break;
            }
        }
        catch (OperationCanceledException)
        {
            EmitStopped(cfg);
        }
    }

    private async Task PlayAuthErrorAsync(CancellationToken ct)
    {
        EmitLog(LogLevel.Info, "Signing in to osu!...");
        await Task.Delay(200, ct).ConfigureAwait(false);
        EmitLog(LogLevel.Error, "Auth failed (HTTP 401). invalid_client");
        Emit(new EngineErrorEvent("Auth failed (HTTP 401). invalid_client"));
        Finish("error");
    }

    private async Task PlaySuccessAsync(AppConfig cfg, CancellationToken ct)
    {
        EmitLog(LogLevel.Info, "Signing in to osu!...");
        EmitLog(LogLevel.Info, "Searching...");
        for (var step = 0; step <= 4; step++)
        {
            EmitProgress(cfg, step, 4, 0, step * 12_000_000);
            await Task.Delay(160, ct).ConfigureAwait(false);
        }

        EmitLog(LogLevel.Info, "Batch 1: 4 sets");
        for (var step = 1; step <= 4; step++)
        {
            EmitLog(LogLevel.Success, $"+ 1000{step} via nerinyan");
            EmitProgress(cfg, step, 4, step, step * 24_000_000);
            await Task.Delay(160, ct).ConfigureAwait(false);
        }

        EmitLog(LogLevel.Success, "Nothing new to download.");
        Emit(new DoneEvent(new RunResultDto(
            "done",
            "Done. 4 downloaded, nothing failed.",
            Summary(12, 4, cfg),
            Array.Empty<FailedDto>(),
            12,
            4,
            8,
            false,
            false,
            1.4,
            new StatsDto(4, 0, 0, 96_000_000, 68_000_000))));
        Finish("done");
    }

    private async Task PlayFailuresAsync(AppConfig cfg, CancellationToken ct)
    {
        EmitLog(LogLevel.Info, "Searching...");
        for (var step = 0; step <= 3; step++)
        {
            EmitProgress(cfg, step, 3, 0, step * 8_000_000);
            await Task.Delay(160, ct).ConfigureAwait(false);
        }

        EmitLog(LogLevel.Success, "+ 20001 via catboy");
        EmitLog(LogLevel.Warning, "! 20002 beatconnect: HTTP 404 (try 1/6)");
        EmitLog(LogLevel.Error, "x 20003 gave up after 6 tries");
        EmitProgress(cfg, 3, 3, 1, 24_000_000);

        var failed = new List<FailedDto>
        {
            new(20002, "Failed Set Two",
                Links(20002)),
            new(20003, "Failed Set Three",
                Links(20003)),
        };

        Emit(new DoneEvent(new RunResultDto(
            "done",
            "Done. 1 downloaded, 2 failed. See the Failed downloads tab.",
            Summary(9, 3, cfg),
            failed,
            9,
            3,
            6,
            false,
            false,
            1.2,
            new StatsDto(1, 2, 0, 24_000_000, 20_000_000))));
        Finish("done");
    }

    private async Task PlayMirrorsExhaustedAsync(AppConfig cfg, CancellationToken ct)
    {
        EmitLog(LogLevel.Info, "Searching...");
        EmitProgress(cfg, 1, 6, 1, 12_000_000);
        await Task.Delay(300, ct).ConfigureAwait(false);
        EmitLog(LogLevel.Warning, "… catboy.best cooling down for 120s");
        EmitLog(LogLevel.Error,
            "Every mirror is rate-limiting us; stopping instead of hammering them. Re-run later.");

        Emit(new DoneEvent(new RunResultDto(
            "paused",
            "Paused safely — stopped early: the mirrors rate-limited this IP. " +
            "Re-run later; finished sets are already recorded.",
            Summary(8, 6, cfg),
            Array.Empty<FailedDto>(),
            8,
            6,
            2,
            true,
            true,
            0.9,
            new StatsDto(1, 0, 0, 12_000_000, 13_000_000))));
        Finish("paused");
    }

    private async Task PlaySlowAsync(AppConfig cfg, CancellationToken ct)
    {
        EmitLog(LogLevel.Info, "Searching...");
        for (var step = 0; step <= 50; step++)
        {
            EmitProgress(cfg, step, 50, Math.Max(0, step - 2), step * 6_000_000L);
            if (step % 5 == 0)
            {
                EmitLog(LogLevel.Info, $"Batch {step / 5 + 1}: transferring");
            }

            await Task.Delay(300, ct).ConfigureAwait(false);
        }

        Emit(new DoneEvent(new RunResultDto(
            "done",
            "Done. 50 downloaded, nothing failed.",
            Summary(50, 50, cfg),
            Array.Empty<FailedDto>(),
            50,
            50,
            0,
            false,
            false,
            15,
            new StatsDto(50, 0, 0, 300_000_000, 20_000_000))));
        Finish("done");
    }

    private void EmitStopped(AppConfig cfg)
    {
        EmitLog(LogLevel.Info, "Stopped by user.");
        Emit(new DoneEvent(new RunResultDto(
            "stopped",
            "Stopped. 0 downloaded this run; finished sets are recorded.",
            Summary(50, 50, cfg),
            Array.Empty<FailedDto>(),
            50,
            50,
            0,
            true,
            false,
            2,
            new StatsDto(0, 0, 0, 0, 0))));
        Finish("stopped");
    }

    private void Finish(string state)
    {
        lock (_lock)
        {
            _state = EngineState.Idle;
        }

        Emit(new StateChangedEvent(state));
    }

    private void EmitProgress(AppConfig cfg, double completed, double total, long ok, long bytes)
    {
        var percent = total > 0 ? completed / total * 100.0 : 0;
        Emit(new ProgressEvent(new ProgressDto(
            $"Downloading {total:0} sets...",
            new OverallDto(completed, total, percent),
            ok > 0
                ? new List<TaskDto>
                {
                    new(1, "20001 Fake Transfer", completed * 128_000, total * 128_000),
                }
                : new List<TaskDto>(),
            new StatsDto(ok, 0, ok > 0 ? 1 : 0, bytes, bytes / 2),
            512.4)));
        _ = cfg;
    }

    private void EmitLog(LogLevel level, string message) =>
        Emit(new LogBatchEvent(new[]
        {
            new LogEntry(DateTimeOffset.Now, level, message),
        }));

    private static IReadOnlyList<RowDto> Summary(int matched, int todo, AppConfig cfg) =>
        UiLabels.SearchRows(matched, todo, cfg)
            .Select(row => new RowDto(row.Key, row.Value)).ToList();

    private static IReadOnlyList<LinkDto> Links(long id) =>
        Util.Links.DirectLinks(id).Select(link => new LinkDto(link.Name, link.Url)).ToList();

    private void Emit(EngineEvent value) => _events.Writer.TryWrite(value);

    private static string Format(double value) =>
        value.ToString(CultureInfo.InvariantCulture);
}
