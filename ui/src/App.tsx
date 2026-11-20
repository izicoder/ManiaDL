import { useEffect, useMemo, useReducer, useRef } from "react";
import { createBridge } from "./bridge/bridge";
import { SettingsPanel } from "./components/SettingsPanel";
import {
  ActiveTable,
  OverallCard,
  RunStatusCard,
  StatsGrid,
} from "./components/StatusCards";
import { Tabs } from "./components/Tabs";
import { reducer, initialState } from "./store/store";
import type { Settings } from "./types";

export default function App() {
  const bridge = useMemo(() => createBridge(), []);
  const [state, dispatch] = useReducer(reducer, initialState);
  const savedJson = useRef<string | null>(null);

  useEffect(() => {
    const unsubscribe = bridge.subscribe((message) =>
      dispatch({ type: "host", message }),
    );
    bridge.post({ type: "ready" });
    return unsubscribe;
  }, [bridge]);

  // When the host pushes settings (init/reset/folder), that becomes the new
  // baseline so the save effect does not echo it straight back.
  useEffect(() => {
    if (state.ready) {
      savedJson.current = JSON.stringify(state.settings);
    }
  }, [state.ready, state.hostSettingsVersion]);

  // Debounced save so the config follows the widgets without a save per keypress.
  useEffect(() => {
    if (!state.ready) {
      return;
    }
    const json = JSON.stringify(state.settings);
    if (json === savedJson.current) {
      return;
    }
    const timer = window.setTimeout(() => {
      savedJson.current = json;
      bridge.post({ type: "saveSettings", settings: state.settings });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [state.settings, state.ready, bridge]);

  const setSetting = (key: keyof Settings, value: string | boolean) =>
    dispatch({ type: "setSetting", key, value });

  const start = () => {
    savedJson.current = JSON.stringify(state.settings);
    bridge.post({ type: "start", settings: state.settings });
  };

  const busy = state.state === "running" || state.state === "stopping";

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>ManiaDL</h1>
          <p className="subtitle">
            bulk osu!mania beatmap downloader for osu!lazer
          </p>
        </div>
        <div className="header-meta">
          {state.appVersion ? <span>v{state.appVersion}</span> : null}
        </div>
      </header>

      <main className="app-main">
        <SettingsPanel
          settings={state.settings}
          envOverride={state.envOverride}
          error={state.error}
          onSetting={setSetting}
          onToggleStatus={(status) =>
            dispatch({ type: "toggleStatus", status })
          }
          onPickFolder={() => bridge.post({ type: "pickFolder" })}
          onOpenUrl={(url) => bridge.post({ type: "openUrl", url })}
          onResetAdvanced={() => bridge.post({ type: "resetSettings" })}
          onDismissError={() => dispatch({ type: "dismissError" })}
        />

        <section className="status-column">
          <RunStatusCard state={state.state} result={state.result} />
          <OverallCard progress={state.progress} />
          <StatsGrid progress={state.progress} />
          <ActiveTable progress={state.progress} />
          <Tabs
            tab={state.tab}
            logs={state.logs}
            failed={state.result?.failed ?? []}
            onTab={(tab) => dispatch({ type: "setTab", tab })}
            onOpenUrl={(url) => bridge.post({ type: "openUrl", url })}
            onCopyText={(text) => bridge.post({ type: "copyText", text })}
          />
        </section>
      </main>

      <footer className="app-footer">
        <span className="footer-message" data-testid="footer-message">
          {state.footer}
        </span>
        <div className="footer-actions">
          <button
            type="button"
            className="ghost-button stop-btn"
            data-testid="stop-btn"
            disabled={!busy}
            onClick={() => bridge.post({ type: "stop" })}
          >
            Stop
          </button>
          <button
            type="button"
            className="primary-button"
            data-testid="start-btn"
            disabled={busy}
            onClick={start}
          >
            Start
          </button>
        </div>
      </footer>

      {state.closeRequested ? (
        <div className="modal-backdrop">
          <div
            className="modal"
            data-testid="confirm-close-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="close-title"
          >
            <h2 id="close-title">Quit ManiaDL?</h2>
            <p>A download is running. Stop it and quit?</p>
            <div className="modal-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={() => dispatch({ type: "dismissClose" })}
              >
                Keep downloading
              </button>
              <button
                type="button"
                className="primary-button"
                data-testid="confirm-close-yes"
                onClick={() => bridge.post({ type: "closeConfirmed" })}
              >
                Stop and quit
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
