import { expect, test } from "@playwright/test";
import {
  SEED_SETTINGS,
  launchApp,
  screenshotPath,
} from "./harness";

test("closing during a run asks first, then exits cleanly", async () => {
  const app = await launchApp({
    name: "close",
    scenario: "slow",
    settings: SEED_SETTINGS,
  });

  try {
    const { page } = app;
    await page.getByTestId("start-btn").click();
    await expect(page.getByTestId("state-chip")).toHaveText("Running");

    app.closeWindow();
    const dialog = page.getByTestId("confirm-close-dialog");
    await expect(dialog).toBeVisible({ timeout: 15000 });
    await page.screenshot({ path: screenshotPath("close-dialog") });

    await page.getByTestId("confirm-close-yes").click();
    const exited = await app.waitForExit(25000);
    expect(exited).toBe(true);
  } finally {
    await app.close(true);
  }
});
