const nf1 = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const nf2 = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatMb(bytes: number): string {
  return `${nf1.format((Number(bytes) || 0) / 1e6)} MB`;
}

export function formatSpeed(bytesPerSecond: number): string {
  return `${nf2.format((Number(bytesPerSecond) || 0) / 1e6)} MB/s`;
}

export function formatFree(gigabytes: number): string {
  if (!Number.isFinite(gigabytes)) {
    return "?";
  }
  return `${nf1.format(gigabytes)} GB`;
}

export function formatPercent(percent: number): string {
  const value = Number.isFinite(percent) ? percent : 0;
  return `${Math.round(value)}%`;
}

export function formatTaskProgress(task: {
  completed: number;
  total: number | null;
}): string {
  const done = Number(task.completed) || 0;
  const total = task.total == null ? null : Number(task.total);
  if (total && total > 0) {
    const pct = Math.min(100, (done / total) * 100);
    return `${pct.toFixed(0).padStart(4)}%   ${formatMb(done)} / ${formatMb(total)}`;
  }
  return formatMb(done);
}

export function overallLabel(completed: number, total: number): string {
  if (!total || total <= 0) {
    return "searching...";
  }
  return `${Math.trunc(completed)} / ${Math.trunc(total)} sets`;
}

export const CHIP_LABELS: Record<string, string> = {
  idle: "Idle",
  running: "Running",
  stopping: "Stopping",
  done: "Done",
  stopped: "Stopped",
  paused: "Paused safely",
  error: "Error",
};
