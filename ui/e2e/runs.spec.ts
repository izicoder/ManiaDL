import { expect, test } from "@playwright/test";
import {
  SEED_SETTINGS,
  launchApp,
  readClipboard,
  screenshotPath,
  type LaunchedApp,
} from "./harness";

async function withApp(
  options: { scenario: string; settings?: Record<string, unknown> | null; name: string },
  body: (app: LaunchedApp) => Promise<void>,
): Promise<void> {
  const app = await launchApp(options);
  try {
    await body(app);
  } finally {
    await app.close(true);
  }
}

test("success run drives the chip, stats, progress and summary", async () => {
  await withApp(
    { name: "success", scenario: "success", settings: SEED_SETTINGS },
    async (app) => {
      const { page } = app;
      const chip = page.getByTestId("state-chip");

      await page.getByTestId("start-btn").click();
      await expect(chip).toHaveText("Running");
      await expect(page.getByTestId("stop-btn")).toBeEnabled();

      await expect(chip).toHaveText("Done", { timeout: 25000 });
      await expect(page.getByTestId("start-btn")).toBeEnabled();
      await expect(page.getByTestId("stop-btn")).toBeDisabled();

      await expect(page.getByTestId("stat-downloaded")).toHaveText("4");
      await expect(page.getByTestId("stat-failed")).toHaveText("0");
      await expect(page.getByTestId("stat-data")).toContainText("MB");
      await expect(page.getByTestId("stat-speed")).toContainText("MB/s");
      await expect(page.getByTestId("stat-free")).toContainText("GB");
      await expect(page.getByTestId("overall-progress")).toHaveAttribute(
        "aria-valuenow",
        "100",
      );
      await expect(
        page.locator(".summary-row", { hasText: "Matching sets" }),
      ).toBeVisible();
      await expect(page.getByTestId("log-line").first()).toBeVisible();
      await expect(page.getByTestId("footer-message")).toContainText("Done");

      await page.screenshot({ path: screenshotPath("success") });
    },
  );
});

test("failures populate the failed tab and Copy links reaches the clipboard", async () => {
  await withApp(
    { name: "failures", scenario: "failures", settings: SEED_SETTINGS },
    async (app) => {
      const { page } = app;
      await page.getByTestId("start-btn").click();
      await expect(page.getByTestId("state-chip")).toHaveText("Done", {
        timeout: 25000,
      });

      await page.getByTestId("tab-failed").click();
      await expect(page.getByTestId("failed-row")).toHaveCount(2);
      await expect(
        page.getByTestId("failed-row").filter({ hasText: "Failed Set Two" }),
      ).toBeVisible();

      await page.getByTestId("copy-links-btn").click();
      const clipboard = await readClipboard(app);
      expect(clipboard).toContain("[20002] Failed Set Two");
      expect(clipboard).toContain("https://osu.ppy.sh/beatmapsets/20002");
      expect(clipboard).toContain("nerinyan");

      await page.screenshot({ path: screenshotPath("failures") });
    },
  );
});

test("slow run stops on demand and re-enables Start", async () => {
  await withApp(
    { name: "slow-stop", scenario: "slow", settings: SEED_SETTINGS },
    async (app) => {
      const { page } = app;
      await page.getByTestId("start-btn").click();
      await expect(page.getByTestId("state-chip")).toHaveText("Running");

      await page.getByTestId("stop-btn").click();
      await expect(page.getByTestId("state-chip")).toHaveText("Stopped", {
        timeout: 25000,
      });
      await expect(page.getByTestId("start-btn")).toBeEnabled();
      await expect(page.getByTestId("stop-btn")).toBeDisabled();

      await page.screenshot({ path: screenshotPath("slow-stop") });
    },
  );
});

test("mirror rate limiting ends paused safely", async () => {
  await withApp(
    {
      name: "mirrors-exhausted",
      scenario: "mirrors-exhausted",
      settings: SEED_SETTINGS,
    },
    async (app) => {
      const { page } = app;
      await page.getByTestId("start-btn").click();
      await expect(page.getByTestId("state-chip")).toHaveText(
        "Paused safely",
        { timeout: 25000 },
      );
      await expect(page.getByTestId("footer-message")).toContainText(
        "Paused safely",
      );
      await page.screenshot({ path: screenshotPath("mirrors-exhausted") });
    },
  );
});
