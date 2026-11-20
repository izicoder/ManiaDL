using ManiaDL.Core.Constants;

namespace ManiaDL.Core.Run;

/// <summary>Chooses the healthiest ready mirror, excluding ones that missed this set.</summary>
public sealed class MirrorScheduler
{
    private readonly RunContext _ctx;

    public MirrorScheduler(RunContext ctx)
    {
        _ctx = ctx;
    }

    /// <summary>
    /// Returns the chosen mirror, or null. <paramref name="wait"/> &gt; 0 means every
    /// mirror host is cooling down and the run should stop.
    /// </summary>
    public (Mirror? Mirror, TimeSpan Wait) Choose(IReadOnlySet<string> tried)
    {
        var now = _ctx.Time.GetUtcNow();
        var ready = MirrorTable.All.Where(mirror => _ctx.Mirrors.State(mirror.Name).Until <= now).ToList();
        if (ready.Count == 0)
        {
            var soonest = MirrorTable.All
                .OrderBy(mirror => _ctx.Mirrors.State(mirror.Name).Until)
                .First();
            var until = _ctx.Mirrors.State(soonest.Name).Until;
            return (null, until > now ? until - now : TimeSpan.Zero);
        }

        var untried = ready.Where(mirror => !tried.Contains(mirror.Name)).ToList();
        if (untried.Count == 0)
        {
            return (null, TimeSpan.Zero);
        }

        var ranked = untried
            .OrderBy(mirror => _ctx.Hosts.Inflight(mirror.Host))
            .ThenBy(mirror => _ctx.Mirrors.State(mirror.Name).Snapshot().Streak)
            .ThenBy(mirror => _ctx.Mirrors.State(mirror.Name).Snapshot().Last)
            .ThenByDescending(mirror => _ctx.Mirrors.State(mirror.Name).Snapshot().Ok)
            .ThenBy(_ => _ctx.Rng.NextDouble())
            .ToList();

        var chosen = ranked[0];
        _ctx.Mirrors.State(chosen.Name).MarkChosen(now);
        return (chosen, TimeSpan.Zero);
    }
}
