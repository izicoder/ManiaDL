import { useState } from "react";
import type { Settings } from "../types";
import {
  ADVANCED_FIELDS,
  SORT_LABELS,
  SORTS,
  STATUS_LABELS,
  STATUS_ORDER,
  parseStatuses,
} from "../store/settings";
import type { UiError } from "../store/store";

export interface SettingsPanelProps {
  settings: Settings;
  envOverride: boolean;
  error: UiError | null;
  onSetting: (key: keyof Settings, value: string | boolean) => void;
  onToggleStatus: (status: string) => void;
  onPickFolder: () => void;
  onOpenUrl: (url: string) => void;
  onResetAdvanced: () => void;
  onDismissError: () => void;
}

function ErrorBanner({
  error,
  onDismiss,
}: {
  error: UiError;
  onDismiss: () => void;
}) {
  return (
    <div className="error-banner" data-testid="error-banner" role="alert">
      <span>{error.message}</span>
      <button
        type="button"
        className="icon-button"
        aria-label="Dismiss error"
        onClick={onDismiss}
      >
        &times;
      </button>
    </div>
  );
}

function sectionForField(field?: string): string {
  if (!field) {
    return "top";
  }
  if (field === "client_id" || field === "client_secret") {
    return "api";
  }
  if (field === "out") {
    return "folder";
  }
  if (
    ["statuses", "keys", "min_sr", "max_sr", "min_favs", "sort", "limit"].includes(
      field,
    )
  ) {
    return "filters";
  }
  if (field === "workers" || field === "batch") {
    return "behaviour";
  }
  return "advanced";
}

export function SettingsPanel(props: SettingsPanelProps) {
  const {
    settings,
    envOverride,
    error,
    onSetting,
    onToggleStatus,
    onPickFolder,
    onOpenUrl,
    onResetAdvanced,
    onDismissError,
  } = props;
  const [showSecret, setShowSecret] = useState(false);
  const statuses = parseStatuses(settings.statuses);
  const errorSection = error ? sectionForField(error.field) : null;

  const banner = (section: string) =>
    error && errorSection === section ? (
      <ErrorBanner error={error} onDismiss={onDismissError} />
    ) : null;

  return (
    <aside className="settings-panel">
      <div className="settings-inner">
        {banner("top")}

        <section className="card settings-section">
          <h2 className="section-title">osu! API</h2>
          <div className="field">
            <label htmlFor="client-id">Client ID</label>
            <input
              id="client-id"
              data-testid="setting-client_id"
              type="text"
              autoComplete="off"
              value={settings.client_id}
              onChange={(event) => onSetting("client_id", event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="client-secret">Client secret</label>
            <div className="input-row">
              <input
                id="client-secret"
                data-testid="setting-client_secret"
                type={showSecret ? "text" : "password"}
                autoComplete="off"
                value={settings.client_secret}
                onChange={(event) =>
                  onSetting("client_secret", event.target.value)
                }
              />
              <button
                type="button"
                className="ghost-button"
                onClick={() => setShowSecret((value) => !value)}
              >
                {showSecret ? "Hide" : "Show"}
              </button>
            </div>
          </div>
          <p className="hint">
            <button
              type="button"
              className="link-button"
              onClick={() => onOpenUrl("https://osu.ppy.sh/home/account/edit")}
            >
              How to get keys
            </button>
            {envOverride ? (
              <span className="env-note">
                Environment credentials override saved keys.
              </span>
            ) : null}
          </p>
          {banner("api")}
        </section>

        <section className="card settings-section">
          <h2 className="section-title">Download folder</h2>
          <div className="field">
            <label htmlFor="out">Folder</label>
            <div className="input-row">
              <input
                id="out"
                data-testid="setting-out"
                type="text"
                value={settings.out}
                onChange={(event) => onSetting("out", event.target.value)}
              />
              <button
                type="button"
                className="ghost-button"
                onClick={onPickFolder}
              >
                Browse
              </button>
            </div>
          </div>
          {banner("folder")}
        </section>

        <section className="card settings-section">
          <h2 className="section-title">Filters</h2>

          <div className="field" data-testid="setting-statuses">
            <span className="field-label">Statuses</span>
            <div className="checkbox-grid">
              {[...STATUS_ORDER, "any"].map((name) => (
                <label key={name} className="checkbox">
                  <input
                    type="checkbox"
                    data-testid={`setting-statuses-${name}`}
                    checked={statuses.includes(name)}
                    onChange={() => onToggleStatus(name)}
                  />
                  <span>{STATUS_LABELS[name]}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="field">
            <label htmlFor="keys">Key counts</label>
            <input
              id="keys"
              data-testid="setting-keys"
              type="text"
              value={settings.keys}
              onChange={(event) => onSetting("keys", event.target.value)}
            />
            <p className="hint">all or 4,7</p>
          </div>

          <div className="field">
            <span className="field-label">Star rating</span>
            <div className="input-row star-row">
              <input
                aria-label="Minimum star rating"
                data-testid="setting-min_sr"
                type="text"
                value={settings.min_sr}
                onChange={(event) => onSetting("min_sr", event.target.value)}
              />
              <span className="muted">to</span>
              <input
                aria-label="Maximum star rating"
                data-testid="setting-max_sr"
                type="text"
                value={settings.max_sr}
                onChange={(event) => onSetting("max_sr", event.target.value)}
              />
            </div>
          </div>

          <div className="field">
            <label htmlFor="min-favs">Min favourites</label>
            <input
              id="min-favs"
              data-testid="setting-min_favs"
              type="text"
              value={settings.min_favs}
              onChange={(event) => onSetting("min_favs", event.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="sort">Sort by</label>
            <select
              id="sort"
              data-testid="setting-sort"
              value={SORTS.includes(settings.sort as (typeof SORTS)[number])
                ? settings.sort
                : SORTS[0]}
              onChange={(event) => onSetting("sort", event.target.value)}
            >
              {SORTS.map((key) => (
                <option key={key} value={key}>
                  {SORT_LABELS[key]}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="limit">Max sets</label>
            <input
              id="limit"
              data-testid="setting-limit"
              type="number"
              min={1}
              value={settings.limit}
              onChange={(event) => onSetting("limit", event.target.value)}
            />
          </div>
          {banner("filters")}
        </section>

        <section className="card settings-section">
          <h2 className="section-title">Download behaviour</h2>
          <div className="field two-up">
            <div>
              <label htmlFor="workers">Parallel downloads</label>
              <input
                id="workers"
                data-testid="setting-workers"
                type="number"
                min={1}
                max={32}
                value={settings.workers}
                onChange={(event) => onSetting("workers", event.target.value)}
              />
            </div>
            <div>
              <label htmlFor="batch">Batch size</label>
              <input
                id="batch"
                data-testid="setting-batch"
                type="number"
                min={1}
                max={500}
                value={settings.batch}
                onChange={(event) => onSetting("batch", event.target.value)}
              />
            </div>
          </div>
          {banner("behaviour")}
        </section>

        <section className="card settings-section">
          <div className="section-head">
            <h2 className="section-title">Advanced filters</h2>
            <button
              type="button"
              className="ghost-button"
              onClick={onResetAdvanced}
            >
              Reset
            </button>
          </div>

          <label className="checkbox">
            <input
              type="checkbox"
              data-testid="advanced-toggle"
              checked={settings.advanced}
              onChange={(event) =>
                onSetting("advanced", event.target.checked)
              }
            />
            <span>Enable advanced filters</span>
          </label>

          <div className={settings.advanced ? "advanced-grid" : "advanced-grid disabled"}>
            {ADVANCED_FIELDS.map(({ key, label, hint }) => (
              <div className="field" key={key}>
                <label htmlFor={`adv-${key}`}>{label}</label>
                <input
                  id={`adv-${key}`}
                  data-testid={`setting-${key}`}
                  type="text"
                  disabled={!settings.advanced}
                  value={String(settings[key] ?? "")}
                  onChange={(event) => onSetting(key, event.target.value)}
                />
                {hint ? <p className="hint">{hint}</p> : null}
              </div>
            ))}

            <label className="checkbox">
              <input
                type="checkbox"
                data-testid="setting-include_nsfw"
                disabled={!settings.advanced}
                checked={settings.include_nsfw}
                onChange={(event) =>
                  onSetting("include_nsfw", event.target.checked)
                }
              />
              <span>Include NSFW sets</span>
            </label>
          </div>
          {banner("advanced")}
        </section>
      </div>
    </aside>
  );
}
