import { useEffect, useRef } from "react";
import type { LogEntry } from "../types";

export function LogTab({ logs }: { logs: LogEntry[] }) {
  const viewRef = useRef<HTMLDivElement | null>(null);
  const stickToBottom = useRef(true);

  useEffect(() => {
    const view = viewRef.current;
    if (view && stickToBottom.current) {
      view.scrollTop = view.scrollHeight;
    }
  }, [logs]);

  const onScroll = () => {
    const view = viewRef.current;
    if (!view) {
      return;
    }
    const distance = view.scrollHeight - view.scrollTop - view.clientHeight;
    stickToBottom.current = distance < 24;
  };

  return (
    <div
      className="log-view"
      data-testid="log-view"
      ref={viewRef}
      onScroll={onScroll}
    >
      {logs.length === 0 ? (
        <p className="muted log-empty">No log lines yet.</p>
      ) : (
        logs.map((entry, index) => (
          <div
            className={`log-line level-${entry.level}`}
            data-testid="log-line"
            data-level={entry.level}
            key={`${entry.t}-${index}`}
          >
            <span className="log-time">
              {new Date(entry.t).toLocaleTimeString("en-GB", {
                hour12: false,
              })}
            </span>
            <span className="log-message">{entry.msg}</span>
          </div>
        ))
      )}
    </div>
  );
}
