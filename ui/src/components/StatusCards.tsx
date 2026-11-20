import type { Progress, RunResult, RunState } from "../types";
import {
  CHIP_LABELS,
  formatFree,
  formatMb,
  formatPercent,
  formatSpeed,
  formatTaskProgress,
  overallLabel,
} from "../format";

export function RunStatusCard({
  state,
  result,
}: {
  state: RunState;
  result: RunResult | null;
}) {
  return (
    <section className="card run-status">
      <div className="card-head">
        <h2 className="card-title">RUN STATUS</h2>
        <span
          className={`state-chip state-${state}`}
          data-testid="state-chip"
          data-state={state}
        >
          {CHIP_LABELS[state] ?? state}
        </span>
      </div>

      {result ? (
        <div className="summary-rows">
          {result.summary.map((row) => (
            <div className="summary-row" key={row.label}>
              <span className="summary-key">{row.label}</span>
              <span className="summary-value">{row.value}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="card-meta">
          Set your filters on the left, then press Start.
        </p>
      )}
    </section>
  );
}

export function OverallCard({ progress }: { progress: Progress }) {
  const { completed, total, percent } = progress.overall;
  return (
    <section className="card overall-card">
      <div className="card-head">
        <h2 className="card-title">OVERALL PROGRESS</h2>
        <span className="card-value accent">{formatPercent(percent)}</span>
      </div>
      <div
        className="progress-track"
        data-testid="overall-progress"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(percent)}
      >
        <div
          className="progress-fill"
          style={{ width: `${Math.max(0, Math.min(100, percent))}%` }}
        />
      </div>
      <p className="card-meta">{overallLabel(completed, total)}</p>
    </section>
  );
}

export function StatsGrid({ progress }: { progress: Progress }) {
  const { stats, freeGb } = progress;
  const cards = [
    {
      id: "stat-downloaded",
      label: "DOWNLOADED",
      value: String(stats.ok),
      tone: "green",
    },
    {
      id: "stat-failed",
      label: "FAILED",
      value: String(stats.fail),
      tone: "red",
    },
    {
      id: "stat-active",
      label: "ACTIVE",
      value: String(stats.active),
      tone: "accent",
    },
    {
      id: "stat-data",
      label: "DATA",
      value: formatMb(stats.bytes),
      tone: "",
    },
    {
      id: "stat-speed",
      label: "SPEED",
      value: formatSpeed(stats.speedBytesPerSecond),
      tone: "",
    },
    {
      id: "stat-free",
      label: "FREE DISK",
      value: formatFree(freeGb),
      tone: "",
    },
  ];

  return (
    <div className="stats-grid">
      {cards.map((card) => (
        <section className="card stat-card" key={card.id}>
          <h3 className="card-title">{card.label}</h3>
          <span
            className={`card-value ${card.tone}`}
            data-testid={card.id}
          >
            {card.value}
          </span>
        </section>
      ))}
    </div>
  );
}

export function ActiveTable({ progress }: { progress: Progress }) {
  return (
    <section className="card active-card">
      <h2 className="card-title">ACTIVE DOWNLOADS</h2>
      <table className="active-table">
        <thead>
          <tr>
            <th>Set</th>
            <th>Progress</th>
          </tr>
        </thead>
        <tbody>
          {progress.active.length === 0 ? (
            <tr>
              <td colSpan={2} className="muted">
                Nothing downloading.
              </td>
            </tr>
          ) : (
            progress.active.map((task) => (
              <tr key={task.id} data-testid="active-row">
                <td className="task-name">{task.description}</td>
                <td className="task-progress">
                  {formatTaskProgress(task)}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
