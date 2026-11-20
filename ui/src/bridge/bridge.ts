import type { HostMessage, UiMessage } from "../types";

/**
 * The tiny transport seam around window.chrome.webview so the UI can run
 * against a fake in tests and a plain browser during Vite development.
 */
export interface BridgeTransport {
  post(message: UiMessage): void;
  subscribe(handler: (message: HostMessage) => void): () => void;
}

interface ChromeWebView {
  postMessage(message: unknown): void;
  addEventListener(
    type: "message",
    listener: (event: { data: unknown }) => void,
  ): void;
  removeEventListener(
    type: "message",
    listener: (event: { data: unknown }) => void,
  ): void;
}

function getWebView(): ChromeWebView | null {
  const chrome = (window as unknown as { chrome?: { webview?: ChromeWebView } })
    .chrome;
  return chrome?.webview ?? null;
}

export function createBridge(): BridgeTransport {
  const webView = getWebView();
  return {
    post(message) {
      if (webView) {
        webView.postMessage(message);
      } else {
        // Vite dev server / plain browser: no host attached.
        console.debug("[bridge] no host; dropped", message.type);
      }
    },
    subscribe(handler) {
      if (!webView) {
        return () => undefined;
      }
      const listener = (event: { data: unknown }) => {
        handler(event.data as HostMessage);
      };
      webView.addEventListener("message", listener);
      return () => webView.removeEventListener("message", listener);
    },
  };
}
