import { useMemo, useState } from "react";
import type { FailedEntry } from "../types";
import type { Tab } from "../store/store";
import { LogTab } from "./LogTab";
import type { LogEntry } from "../types";

export function linksText(entries: FailedEntry[]): string {
  const lines: string[] = ["ManiaDL failed downloads", ""];
  for (const entry of entries) {
    lines.push(`[${entry.id}] ${entry.title}`);
    for (const link of entry.links) {
      lines.push(`  ${link.name.padEnd(12)} ${link.url}`);
    }
    lines.push("");
  }
  return lines.join("\n");
}

function osuUrl(entry: FailedEntry): string {
  const osu = entry.links.find((link) => link.name === "osu!");
  return osu ? osu.url : `https://osu.ppy.sh/beatmapsets/${entry.id}`;
}

export interface TabsProps {
  tab: Tab;
  logs: LogEntry[];
  failed: FailedEntry[];
  onTab: (tab: Tab) => void;
  onOpenUrl: (url: string) => void;
  onCopyText: (text: string) => void;
}

export function Tabs(props: TabsProps) {
  const { tab, logs, failed, onTab, onOpenUrl, onCopyText } = props;
  const [selected, setSelected] = useState<number | null>(null);

  const selectedEntries = useMemo(() => {
    if (selected == null) {
      return failed;
    }
    return failed.filter((entry) => entry.id === selected);
  }, [failed, selected]);

  const copy = () => {
    const entries = selectedEntries.length > 0 ? selectedEntries : failed;
    if (entries.length > 0) {
      onCopyText(linksText(entries));
    }
  };

  return (
    <section className="card tabs-card">
      <div className="tab-bar" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "log"}
          className={tab === "log" ? "tab active" : "tab"}
          data-testid="tab-log"
          onClick={() => onTab("log")}
        >
          Log
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "failed"}
          className={tab === "failed" ? "tab active" : "tab"}
          data-testid="tab-failed"
          onClick={() => onTab("failed")}
        >
          Failed downloads{failed.length > 0 ? ` (${failed.length})` : ""}
        </button>
      </div>

      {tab === "log" ? (
        <LogTab logs={logs} />
      ) : (
        <div className="failed-tab" role="tabpanel">
          <div className="failed-actions">
            <button
              type="button"
              className="ghost-button"
              disabled={selectedEntries.length === 0}
              onClick={() => {
                const entry = selectedEntries[0];
                if (entry) {
                  onOpenUrl(osuUrl(entry));
                }
              }}
            >
              Open osu! page
            </button>
            <button
              type="button"
              className="ghost-button"
              data-testid="copy-links-btn"
              disabled={failed.length === 0}
              onClick={copy}
            >
              Copy links
            </button>
            <span className="hint">
              Double-click a row to open its osu! page.
            </span>
          </div>

          <div className="failed-view">
            {failed.length === 0 ? (
              <p className="muted">
                No failed downloads. Failures appear here after a run.
              </p>
            ) : (
              <table className="failed-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Title</th>
                  </tr>
                </thead>
                <tbody>
                  {failed.map((entry) => (
                    <tr
                      key={entry.id}
                      data-testid="failed-row"
                      className={
                        selected === entry.id ? "failed-row selected" : "failed-row"
                      }
                      onClick={() => setSelected(entry.id)}
                      onDoubleClick={() => onOpenUrl(osuUrl(entry))}
                    >
                      <td className="failed-id">{entry.id}</td>
                      <td>{entry.title}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
