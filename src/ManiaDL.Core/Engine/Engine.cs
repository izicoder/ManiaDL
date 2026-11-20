using System.Threading.Channels;
using ManiaDL.Core.Config;
using ManiaDL.Core.Constants;
using ManiaDL.Core.Logging;
using ManiaDL.Core.Progress;
using ManiaDL.Core.Run;
using ManiaDL.Core.Ui;
using ManiaDL.Core.Util;

namespace ManiaDL.Core.Engine;

/// <summary>
/// Facade the host talks to: validate, save settings, launch one run, forward logs,
/// coalesced progress and the formatted result. No global state.
/// </summary>
public sealed class Engine : IEngine
{
    private readonly AppPaths _paths;
    private readonly ConfigStore _store;
    private readonly TimeProvider _time;
    private readonly Random _rng;
    private readonly Func<RunContext, DownloadOrchestrator> _orchestratorFactory;
    private readonly Channel<EngineEvent> _events =
        Channel.CreateUnbounded<EngineEvent>(new UnboundedChannelOptions { SingleReader = true });

    private readonly object _lock = new();
    private RunContext? _ctx;
    private AppConfig? _cfg;
    private DateTimeOffset _startedAt;
    private volatile EngineState _state = EngineState.Idle;

    public Engine(
        AppPaths paths,
        ConfigStore store,
        TimeProvider? time = null,
        Random? rng = null,
        Func<RunContext, DownloadOrchestrator>? orchestratorFactory = null)
    {
        _paths = paths;
        _store = store;
        _time = time ?? TimeProvider.System;
        _rng = rng ?? Random.Shared;
        _orchestratorFactory = orchestratorFactory ?? (ctx => new DownloadOrchestrator(ctx));
    }

    public EngineState State => _state;

    public ChannelReader<EngineEvent> Events => _events.Reader;

    public Task<StartOutcome> StartAsync(RawConfig raw)
    {
        RunContext ctx;
        AppConfig cfg;
        string clientId;
        string secret;

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

            clientId = (raw.ClientId ?? "").Trim();
            secret = (raw.ClientSecret ?? "").Trim();
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

            ctx = new RunContext(
                new CancellationTokenSource(),
                new RunLog(_time),
                new TaskBoard(),
                _time,
                _rng);
            _ctx = ctx;
            _cfg = cfg;
            _startedAt = _time.GetUtcNow();
            _state = EngineState.Running;
        }

        Emit(new StateChangedEvent("running"));
        _ = PumpLogsAsync(ctx);
        _ = PumpProgressAsync(ctx);
        _ = ExecuteAsync(cfg, clientId, secret, ctx);
        return Task.FromResult(StartOutcome.Ok());
    }

    public void Stop()
    {
        lock (_lock)
        {
            if (_state != EngineState.Running || _ctx is null)
            {
                return;
            }

            _state = EngineState.Stopping;
            _ctx.Stop.Cancel();
        }

        Emit(new StateChangedEvent("stopping"));
    }

    private async Task ExecuteAsync(AppConfig cfg, string clientId, string secret, RunContext ctx)
    {
        try
        {
            var orchestrator = _orchestratorFactory(ctx);
            var result = await orchestrator.RunAsync(cfg, clientId, secret).ConfigureAwait(false);
            Emit(new ProgressEvent(BuildProgress(ctx, cfg)));
            var dto = BuildResultDto(result, cfg, ctx);
            Emit(new DoneEvent(dto));
            Finish(dto.State);
        }
        catch (OperationCanceledException)
        {
            Emit(new ProgressEvent(BuildProgress(ctx, cfg)));
            var dto = StoppedResult(cfg, ctx);
            Emit(new DoneEvent(dto));
            Finish(dto.State);
        }
        catch (AuthFatalException ex)
        {
            if (ex.ClearCredentials)
            {
                var saved = _store.Load();
                if (saved.ClientId.Length > 0 || saved.ClientSecret.Length > 0)
                {
                    saved.ClientId = "";
                    saved.ClientSecret = "";
                    _store.Save(saved, ctx.Log);
                    ctx.Log.Warning("Saved credentials removed; please check and re-enter them.");
                }
            }

            ctx.Log.Warning(ApiEndpoints.KeyGuide);
            ctx.Log.Error(ex.Message);
            Emit(new EngineErrorEvent(ex.Message));
            Finish("error");
        }
        catch (EngineFatalException ex)
        {
            ctx.Log.Error(ex.Message);
            Emit(new EngineErrorEvent(ex.Message));
            Finish("error");
        }
        catch (Exception ex)
        {
            var message = $"{ex.GetType().Name}: {ex.Message}";
            ctx.Log.Error(message);
            Emit(new EngineErrorEvent(message));
            Finish("error");
        }
    }

    private void Finish(string state)
    {
        lock (_lock)
        {
            _state = EngineState.Idle;
        }

        Emit(new StateChangedEvent(state));
    }

    private async Task PumpLogsAsync(RunContext ctx)
    {
        try
        {
            await foreach (var entry in ctx.Log.Reader.ReadAllAsync().ConfigureAwait(false))
            {
                var batch = new List<LogEntry> { entry };
                while (batch.Count < 200 && ctx.Log.Reader.TryRead(out var extra))
                {
                    batch.Add(extra);
                }

                Emit(new LogBatchEvent(batch));
            }
        }
        catch (OperationCanceledException)
        {
            // Engine shutdown.
        }
    }

    private async Task PumpProgressAsync(RunContext ctx)
    {
        while (_state is EngineState.Running or EngineState.Stopping)
        {
            var cfg = _cfg;
            if (cfg is not null)
            {
                Emit(new ProgressEvent(BuildProgress(ctx, cfg)));
            }

            try
            {
                await Task.Delay(TimeSpan.FromMilliseconds(120), _time).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                return;
            }
        }
    }

    private ProgressDto BuildProgress(RunContext ctx, AppConfig cfg)
    {
        var snapshot = ctx.Progress.Snapshot();
        var all = snapshot.Tasks.FirstOrDefault(task => task.Description == "all");
        var completed = all?.Completed ?? 0;
        var total = all?.Total ?? 0;
        var percent = total > 0 ? completed / total * 100.0 : 0.0;
        var stats = ctx.Stats.Snapshot();
        var elapsed = Math.Max((_time.GetUtcNow() - _startedAt).TotalSeconds, 1.0);

        return new ProgressDto(
            snapshot.Message,
            new OverallDto(completed, total, percent),
            snapshot.Tasks
                .Where(task => task.Description != "all")
                .Select(task => new TaskDto(task.Id, task.Description, task.Completed, task.Total))
                .ToList(),
            new StatsDto(stats.Ok, stats.Fail, stats.Active, stats.Bytes, stats.Bytes / elapsed),
            ctx.Disk.FreeGb(cfg.Out));
    }

    private RunResultDto BuildResultDto(RunResult result, AppConfig cfg, RunContext ctx)
    {
        var stats = ctx.Stats.Snapshot();
        var state = result.MirrorsExhausted ? "paused" : result.Stopped ? "stopped" : "done";

        var failedNow = result.NewFailed.Count;
        var oldFailed = result.Failed.Count;
        string footer;
        if (result.Stopped)
        {
            footer = $"Stopped. {stats.Ok} downloaded this run; finished sets are recorded.";
        }
        else if (result.Todo == 0)
        {
            footer = "Nothing new to download.";
        }
        else if (failedNow > 0)
        {
            footer = $"Done. {stats.Ok} downloaded, {failedNow} failed. See the Failed downloads tab.";
        }
        else if (oldFailed > 0)
        {
            footer = $"Done. {stats.Ok} downloaded; {oldFailed} earlier failure(s) remain in the Failed tab.";
        }
        else
        {
            footer = $"Done. {stats.Ok} downloaded, nothing failed.";
        }

        if (result.MirrorsExhausted)
        {
            footer = "Paused safely — stopped early: the mirrors rate-limited this IP. " +
                     "Re-run later; finished sets are already recorded.";
        }

        return new RunResultDto(
            state,
            footer,
            UiLabels.SearchRows(result.Matched, result.Todo, cfg)
                .Select(row => new RowDto(row.Key, row.Value)).ToList(),
            FailedReport.FailedEntries(result.Failed.Keys, result.Titles)
                .Select(entry => new FailedDto(
                    entry.Id,
                    entry.Title,
                    entry.DirectLinks.Select(link => new LinkDto(link.Name, link.Url)).ToList()))
                .ToList(),
            result.Matched,
            result.Todo,
            result.Existing,
            result.Stopped,
            result.MirrorsExhausted,
            result.Elapsed,
            new StatsDto(stats.Ok, stats.Fail, stats.Active, stats.Bytes, 0));
    }

    private RunResultDto StoppedResult(AppConfig cfg, RunContext ctx)
    {
        var stats = ctx.Stats.Snapshot();
        return new RunResultDto(
            "stopped",
            "Stopped. Finished sets are recorded.",
            UiLabels.SearchRows(0, 0, cfg).Select(row => new RowDto(row.Key, row.Value)).ToList(),
            Array.Empty<FailedDto>(),
            0,
            0,
            0,
            true,
            false,
            0,
            new StatsDto(stats.Ok, stats.Fail, stats.Active, stats.Bytes, 0));
    }

    private void Emit(EngineEvent value) => _events.Writer.TryWrite(value);
}
