/**
 * Playwright: dashboard wired to Light's Scenario A cached loop.
 */
import { test, expect } from "@playwright/test";

test.describe("BREAKOUT dashboard e2e", () => {
  test("scenario A fills sky map, candidates, countdown, ADS links, Simulated badges", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => consoleErrors.push(String(err)));

    await page.goto("/");
    await expect(page.locator(".brand")).toBeVisible();

    // Start Scenario A (galactic CCSN / Betelgeuse) from the dashboard button.
    const startBtn = page.locator(
      'button[data-scenario="scenario_a_galactic_ccsn"]',
    );
    await expect(startBtn).toBeVisible();
    await startBtn.click();

    // Sky map renders (Mollweide PNG from fuse).
    const skyImg = page.locator(".sky-img");
    await expect(skyImg).toBeVisible({ timeout: 90_000 });
    await expect
      .poll(async () => skyImg.evaluate((el: HTMLImageElement) => el.naturalWidth), {
        timeout: 90_000,
      })
      .toBeGreaterThan(0);

    // At least one candidate row.
    const rows = page.locator(".cand-table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 60_000 });
    await expect(rows).toHaveCount(await rows.count());
    expect(await rows.count()).toBeGreaterThanOrEqual(1);

    // Breakout countdown (class_window + elapsed since t0).
    const countdown = page.locator(".cand-table tbody tr .breakout").first();
    await expect(countdown.locator(".bw")).toBeVisible();
    await expect(countdown.locator(".elapsed")).toBeVisible();
    await expect(countdown.locator(".bw")).not.toHaveText("");
    await expect(countdown.locator(".elapsed")).not.toHaveText("");

    // Click first candidate → ADS evidence links.
    await rows.first().click();
    const adsLink = page.locator(".evidence-list a").first();
    await expect(adsLink).toBeVisible({ timeout: 30_000 });
    const href = await adsLink.getAttribute("href");
    expect(href).toBeTruthy();
    expect(href!).toMatch(/^https:\/\/ui\.adsabs\.harvard\.edu\/abs\//);
    await expect(adsLink).toHaveAttribute("target", "_blank");

    // Simulated badges visible (Scenario A payloads are simulated=true).
    const simBadges = page.locator(".badge.simulated:visible");
    await expect(simBadges.first()).toBeVisible();
    expect(await simBadges.count()).toBeGreaterThanOrEqual(1);

    expect(consoleErrors, `console errors: ${consoleErrors.join(" | ")}`).toEqual(
      [],
    );
  });
});
