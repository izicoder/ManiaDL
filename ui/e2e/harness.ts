/**
 * E2E harness: launches the real WinForms host with a scripted engine, then
 * attaches Playwright to the WebView2 instance over CDP. No Playwright browser
 * download is needed because the UI already runs inside WebView2.
 */
import { chromium, type Browser, type Page } from "@playwright/test";
import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { createServer } from "node:net";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

export const repoRoot = path.resolve(here, "..", "..");
export const artifactsDir = path.join(here, "artifacts");

const DEFAULT_EXE = path.join(
  repoRoot,
  "src",
  "ManiaDL.Host",
  "bin",
  "Debug",
  "net8.0-windows",
  "ManiaDL.exe",
);

export const exePath = process.env.MANIADL_EXE || DEFAULT_EXE;

export const SEED_SETTINGS = {
  client_id: "12345",
  client_secret: "test-secret",
  out: "",
  statuses: "ranked",
  keys: "4",
  min_sr: "0",
  max_sr: "99",
  min_favs: "0",
  sort: "favourites_desc",
  limit: "40",
  workers: "2",
  batch: "5",
  advanced: false,
  query: "",
  title: "",
  artist: "",
  creator: "",
  source: "",
  exclude: "",
  genre: "",
  language: "",
  bpm_range: "",
  length_range: "",
  notes_range: "",
  min_plays: "0",
  ranked_range: "",
  include_nsfw: false,
};

async function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close(() => resolve(port));
    });
  });
}

async function waitForCdp(port: number, timeoutMs = 30000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (response.ok) {
        return;
      }
    } catch {
      // Not listening yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw new Error(`WebView2 CDP endpoint did not appear on port ${port}`);
}

export interface LaunchOptions {
  scenario: string;
  settings?: Record<string, unknown> | null;
  name: string;
}

export interface LaunchedApp {
  browser: Browser;
  page: Page;
  dataDir: string;
  process: ChildProcess;
  clipboardPath: string;
  close: (force?: boolean) => Promise<void>;
  closeWindow: () => void;
  waitForExit: (timeoutMs: number) => Promise<boolean>;
}

export async function launchApp(options: LaunchOptions): Promise<LaunchedApp> {
  if (!existsSync(exePath)) {
    throw new Error(
      `ManiaDL.exe not found at ${exePath}. Run scripts/e2e.ps1 or build the host first.`,
    );
  }

  mkdirSync(artifactsDir, { recursive: true });
  const dataDir = mkdtempSync(path.join(tmpdir(), "maniadl-e2e-"));
  const outDir = path.join(dataDir, "downloads");
  mkdirSync(outDir, { recursive: true });

  if (options.settings) {
    const settings = { ...options.settings };
    if (!settings.out) {
      settings.out = outDir;
    }
    writeFileSync(
      path.join(dataDir, "mania_dl_config.json"),
      JSON.stringify(settings, null, 2),
      "utf8",
    );
  }

  const port = await freePort();
  const child = spawn(
    exePath,
    [
      "--debug-port",
      String(port),
      "--fake-engine",
      options.scenario,
      "--data-dir",
      dataDir,
    ],
    { stdio: "ignore", windowsHide: false },
  );

  let exited = false;
  child.once("exit", () => {
    exited = true;
  });

  const deadline = Date.now() + 30000;
  let browser: Browser | null = null;
  let page: Page | null = null;
  while (Date.now() < deadline && !page) {
    if (exited) {
      throw new Error("ManiaDL exited before the UI became available.");
    }
    try {
      await waitForCdp(port, 1000);
      browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
      const pages = browser.contexts().flatMap((context) => context.pages());
      page =
        pages.find((candidate) => candidate.url().startsWith("https://maniadl.app")) ??
        pages.find((candidate) => !candidate.url().startsWith("devtools")) ??
        null;
      if (!page) {
        await browser.close();
        browser = null;
      }
    } catch {
      browser = null;
      page = null;
    }
    if (!page) {
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }

  if (!browser || !page) {
    child.kill();
    throw new Error("Could not attach to the ManiaDL WebView2 UI.");
  }

  await page.waitForSelector('[data-testid="start-btn"]', { timeout: 20000 });

  const clipboardPath = path.join(dataDir, "clipboard.txt");

  return {
    browser,
    page,
    dataDir,
    process: child,
    clipboardPath,
    closeWindow() {
      if (!child.pid || exited) {
        return;
      }
      const script = [
        `$p = Get-Process -Id ${child.pid} -ErrorAction Stop;`,
        "Add-Type -Name Win32 -Namespace Native -MemberDefinition",
        "'[DllImport(\"user32.dll\", SetLastError=true)] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);';",
        "[Native.Win32]::PostMessage($p.MainWindowHandle, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null;",
      ].join(" ");
      try {
        execFileSync("powershell.exe", ["-NoProfile", "-Command", script], {
          stdio: "ignore",
        });
      } catch {
        // Window already closing.
      }
    },
    async waitForExit(timeoutMs) {
      const deadline = Date.now() + timeoutMs;
      while (Date.now() < deadline) {
        if (exited || child.exitCode !== null) {
          return true;
        }
        await new Promise((resolve) => setTimeout(resolve, 150));
      }
      return exited || child.exitCode !== null;
    },
    async close(force = false) {
      try {
        await browser?.close();
      } catch {
        // CDP may vanish when the process exits.
      }
      if (!exited) {
        if (process.platform === "win32" && child.pid) {
          try {
            execFileSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
              stdio: "ignore",
            });
          } catch {
            // Already gone.
          }
        } else {
          child.kill("SIGKILL");
        }
      }
      if (force) {
        // WebView2 keeps its profile files briefly after the process exits.
        for (let attempt = 0; attempt < 20; attempt++) {
          try {
            rmSync(dataDir, { recursive: true, force: true });
            break;
          } catch {
            await new Promise((resolve) => setTimeout(resolve, 150));
          }
        }
      }
    },
  };
}

export function screenshotPath(name: string): string {
  return path.join(artifactsDir, `${name}.png`);
}

export async function readClipboard(app: LaunchedApp): Promise<string> {
  for (let attempt = 0; attempt < 40; attempt++) {
    if (existsSync(app.clipboardPath)) {
      return readFileSync(app.clipboardPath, "utf8");
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  return "";
}
