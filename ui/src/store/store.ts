import type {
  HostMessage,
  LogEntry,
  Progress,
  RunResult,
  RunState,
  Settings,
} from "../types";
import {
  autoEnableAdvanced,
  normaliseSettings,
  parseStatuses,
  statusesToRaw,
  toggleStatus,
} from "./settings";

export type Tab = "log" | "failed";

export interface UiError {
  message: string;
  field?: string;
}

export interface UiState {
  ready: boolean;
  appVersion: string;
  settings: Settings;
  envOverride: boolean;
  state: RunState;
  footer: string;
  progress: Progress;
  logs: LogEntry[];
  result: RunResult | null;
  error: UiError | null;
  tab: Tab;
  closeRequested: boolean;
  /** Bumped whenever the host pushes settings, so the save effect can rebase. */
  hostSettingsVersion: number;
  folderPicked: string | null;
}

export type UiAction =
  | { type: "host"; message: HostMessage }
  | { type: "setSetting"; key: keyof Settings; value: string | boolean }
  | { type: "toggleStatus"; status: string }
  | { type: "setTab"; tab: Tab }
  | { type: "dismissError" }
  | { type: "dismissClose" };

export const EMPTY_PROGRESS: Progress = {
  message: "",
  overall: { completed: 0, total: 0, percent: 0 },
  active: [],
  stats: { ok: 0, fail: 0, active: 0, bytes: 0, speedBytesPerSecond: 0 },
  freeGb: 0,
};

export const INITIAL_FOOTER = "Set your filters on the left, then press Start.";

export const initialState: UiState = {
  ready: false,
  appVersion: "",
  settings: normaliseSettings(null),
  envOverride: false,
  state: "idle",
  footer: INITIAL_FOOTER,
  progress: EMPTY_PROGRESS,
  logs: [],
  result: null,
  error: null,
  tab: "log",
  closeRequested: false,
  hostSettingsVersion: 0,
  folderPicked: null,
};

function withRuntimeSettings(settings: Settings): Settings {
  const normalised = normaliseSettings(settings);
  return { ...normalised, advanced: autoEnableAdvanced(normalised) };
}

export function reducer(state: UiState, action: UiAction): UiState {
  switch (action.type) {
    case "host":
      return reduceHost(state, action.message);
    case "setSetting":
      return {
        ...state,
        settings: { ...state.settings, [action.key]: action.value },
      };
    case "toggleStatus": {
      const current = parseStatuses(state.settings.statuses);
      return {
        ...state,
        settings: {
          ...state.settings,
          statuses: statusesToRaw(toggleStatus(current, action.status)),
        },
      };
    }
    case "setTab":
      return { ...state, tab: action.tab };
    case "dismissError":
      return { ...state, error: null };
    case "dismissClose":
      return { ...state, closeRequested: false };
    default:
      return state;
  }
}

function reduceHost(state: UiState, message: HostMessage): UiState {
  switch (message.type) {
    case "init": {
      const settings = withRuntimeSettings(message.settings);
      return {
        ...state,
        ready: true,
        appVersion: message.appVersion ?? "",
        settings,
        envOverride: Boolean(message.envOverride),
        hostSettingsVersion: state.hostSettingsVersion + 1,
        state: "idle",
        footer: INITIAL_FOOTER,
      };
    }
    case "settings":
      return {
        ...state,
        settings: withRuntimeSettings(message.settings),
        hostSettingsVersion: state.hostSettingsVersion + 1,
        error: null,
      };
    case "state": {
      const next = (message.state ?? "idle") as RunState;
      if (next === "running") {
        return {
          ...state,
          state: next,
          footer: "Signing in...",
          logs: [],
          result: null,
          error: null,
          progress: EMPTY_PROGRESS,
          tab: "log",
        };
      }
      return { ...state, state: next };
    }
    case "log": {
      if (!Array.isArray(message.entries) || message.entries.length === 0) {
        return state;
      }
      const merged = [...state.logs, ...message.entries];
      return {
        ...state,
        logs: merged.length > 3000 ? merged.slice(merged.length - 3000) : merged,
      };
    }
    case "progress": {
      const value = message.value;
      if (!value) {
        return state;
      }
      return {
        ...state,
        progress: value,
        footer: value.message ? value.message : state.footer,
      };
    }
    case "done":
      return {
        ...state,
        result: message.result,
        state: (message.result.state as RunState) ?? "done",
        footer: message.result.footer,
      };
    case "error":
      return {
        ...state,
        error: {
          message: message.message,
          field: message.field ?? undefined,
        },
        footer: message.message,
      };
    case "folderPicked":
      return {
        ...state,
        folderPicked: message.path,
        settings: { ...state.settings, out: message.path },
      };
    case "closeRequested":
      return { ...state, closeRequested: true };
    default:
      return state;
  }
}
