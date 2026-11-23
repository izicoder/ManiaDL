/**
 * Types mirroring the bridge protocol. The host serialises camelCase JSON;
 * settings keep the snake_case config keys.
 */

export type LogLevel = "info" | "success" | "warning" | "error" | "muted";

export interface LogEntry {
  t: string;
  level: LogLevel;
  msg: string;
}

/** Raw settings, exactly as stored in mania_dl_config.json. */
export interface Settings {
  client_id: string;
  client_secret: string;
  out: string;
  statuses: string;
  keys: string;
  min_sr: string;
  max_sr: string;
  min_favs: string;
  sort: string;
  limit: string;
  workers: string;
  batch: string;
  advanced: boolean;
  query: string;
  title: string;
  artist: string;
  creator: string;
  source: string;
  exclude: string;
  genre: string;
  language: string;
  bpm_range: string;
  length_range: string;
  notes_range: string;
  min_plays: string;
  ranked_range: string;
  include_nsfw: boolean;
}

export interface Overall {
  completed: number;
  total: number;
  percent: number;
}

export interface TaskItem {
  id: number;
  description: string;
  completed: number;
  total: number | null;
}

export interface Stats {
  ok: number;
  fail: number;
  active: number;
  bytes: number;
  speedBytesPerSecond: number;
}

export interface Progress {
  message: string;
  overall: Overall;
  active: TaskItem[];
  stats: Stats;
  freeGb: number;
}

export interface Row {
  label: string;
  value: string;
}

export interface Link {
  name: string;
  url: string;
}

export interface FailedEntry {
  id: number;
  title: string;
  links: Link[];
}

export interface RunResult {
  state: string;
  footer: string;
  summary: Row[];
  failed: FailedEntry[];
  matched: number;
  todo: number;
  existing: number;
  stopped: boolean;
  mirrorsExhausted: boolean;
  elapsed: number;
  stats: Stats;
}

export type RunState =
  | "idle"
  | "running"
  | "stopping"
  | "done"
  | "stopped"
  | "paused"
  | "error";

export type HostMessage =
  | {
      type: "init";
      protocolVersion: number;
      appVersion: string;
      settings: Settings;
      envOverride?: boolean;
      failed?: unknown[];
    }
  | { type: "settings"; settings: Settings }
  | { type: "state"; state: RunState; detail?: string | null }
  | { type: "log"; entries: LogEntry[] }
  | { type: "progress"; value: Progress }
  | { type: "done"; result: RunResult }
  | { type: "error"; message: string; field?: string | null }
  | { type: "folderPicked"; path: string }
  | { type: "closeRequested" };

export type UiMessage =
  | { type: "ready" }
  | { type: "saveSettings"; settings: Settings }
  | { type: "resetSettings" }
  | { type: "start"; settings: Settings }
  | { type: "stop" }
  | { type: "openUrl"; url: string }
  | { type: "copyText"; text: string }
  | { type: "pickFolder" }
  | { type: "closeConfirmed" };
