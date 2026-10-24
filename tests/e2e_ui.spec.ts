/**
 * Playwright dashboard test. Placeholder — filled in a later prompt.
 */
import { test, expect } from "@playwright/test";

test.skip("dashboard loads (placeholder)", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("body")).toBeVisible();
});
