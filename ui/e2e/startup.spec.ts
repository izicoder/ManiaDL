import { expect, test } from "@playwright/test";
import {
  SEED_SETTINGS,
  launchApp,
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

test("startup shows settings seeded in the data dir", async () => {
  await withApp(
    {
      name: "startup",
      scenario: "success",
      settings: {
        ...SEED_SETTINGS,
        keys: "4,7",
        limit: "123",
        min_sr: "4.5",
      },
    },
    async (app) => {
      const { page } = app;
      await expect(page.getByTestId("setting-keys")).toHaveValue("4,7");
      await expect(page.getByTestId("setting-limit")).toHaveValue("123");
      await expect(page.getByTestId("setting-min_sr")).toHaveValue("4.5");
      await expect(page.getByTestId("setting-out")).toHaveValue(/downloads$/);
      await expect(page.getByTestId("setting-statuses-ranked")).toBeChecked();
      await expect(page.getByTestId("state-chip")).toHaveText("Idle");
      await page.screenshot({ path: screenshotPath("startup") });
    },
  );
});

test("advanced gate and status checkbox rules", async () => {
  await withApp(
    {
      name: "advanced",
      scenario: "success",
      settings: { ...SEED_SETTINGS, statuses: "any", advanced: false },
    },
    async (app) => {
      const { page } = app;
      const toggle = page.getByTestId("advanced-toggle");
      await expect(toggle).not.toBeChecked();
      await expect(page.getByTestId("setting-query")).toBeDisabled();

      await toggle.check();
      await expect(page.getByTestId("setting-query")).toBeEnabled();

      const any = page.getByTestId("setting-statuses-any");
      const ranked = page.getByTestId("setting-statuses-ranked");
      await expect(any).toBeChecked();
      await expect(ranked).not.toBeChecked();

      await ranked.check();
      await expect(any).not.toBeChecked();
      await expect(ranked).toBeChecked();

      // Unticking the last real status restores Ranked.
      await ranked.click();
      await expect(ranked).toBeChecked();
      await expect(any).not.toBeChecked();

      await page.screenshot({ path: screenshotPath("advanced-status") });
    },
  );
});

test("missing credentials puts an error banner on the credential field", async () => {
  await withApp(
    {
      name: "missing-credentials",
      scenario: "success",
      settings: { ...SEED_SETTINGS, client_id: "", client_secret: "" },
    },
    async (app) => {
      const { page } = app;
      await page.getByTestId("start-btn").click();
      const banner = page.getByTestId("error-banner");
      await expect(banner).toBeVisible();
      await expect(banner).toContainText("client ID");
      await expect(page.getByTestId("state-chip")).toHaveText("Idle");
      await page.screenshot({ path: screenshotPath("missing-credentials") });
    },
  );
});
