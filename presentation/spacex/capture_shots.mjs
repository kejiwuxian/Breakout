/**
 * Capture SpaceX-track production screenshots (1920×1080) for the pitch deck.
 * Usage: node presentation/spacex/capture_shots.mjs
 */
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const BASE = process.env.DEMO_BASE_URL || "https://supernova.lylinks.com/spacex";
const OUT = process.env.DEMO_OUT || "/opt/cursor/artifacts/presentation/shots";
const VIEWPORT = { width: 1920, height: 1080 };

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function shot(page, name) {
  const dest = path.join(OUT, name);
  await page.screenshot({ path: dest, fullPage: false });
  console.log("saved", dest);
  return dest;
}

async function main() {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: "/usr/local/bin/google-chrome",
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 1,
  });
  const page = context.newPage ? await context.newPage() : await browser.newPage();
  page.setDefaultTimeout(90_000);

  console.log("Opening", BASE + "/");
  await page.goto(BASE + "/", { waitUntil: "networkidle", timeout: 90_000 });
  await page.waitForSelector(".brand, .wordmark, header", { timeout: 60_000 });
  await wait(2800);
  await shot(page, "spacex-demo-16x9-idle.png");

  // About
  const about = page.locator("a.nav-about, a[href*='about'], button:has-text('About')").first();
  if (await about.count()) {
    await about.click();
    await wait(900);
    await shot(page, "spacex-demo-16x9-about.png");
    const back = page.locator("#brand-link, a.about-back, button:has-text('Back')").first();
    if (await back.count()) await back.click();
    else await page.goto(BASE + "/", { waitUntil: "networkidle" });
    await wait(800);
  }

  await page.waitForSelector(".event-card, .scenario-card, button:has-text('IceCube')", {
    timeout: 30_000,
  }).catch(() => {});
  await shot(page, "spacex-demo-16x9-event-cards.png");

  // IceCube replay
  const ice = page
    .locator("button.event-card, button.scenario-card, .event-card, .scenario-card, button")
    .filter({ hasText: /IceCube/i })
    .first();
  if (await ice.count()) {
    await ice.click();
    await wait(5500);
    await shot(page, "spacex-demo-16x9-icecube.png");
    // candidate row
    const row = page.locator(".obj-row, tr.candidate, .candidate-row").first();
    if (await row.count()) {
      await row.click();
      await wait(1200);
      await shot(page, "spacex-demo-16x9-candidate-selected.png");
      await wait(800);
      await shot(page, "spacex-demo-16x9-candidate-detail.png");
    }
  }

  // Subscribe / endpoints — scroll rail into view
  await page.evaluate(() => {
    const el =
      document.querySelector("#panel-subscribe") ||
      document.querySelector(".subscribe-panel") ||
      document.querySelector("[data-panel='subscribe']");
    if (el) el.scrollIntoView({ block: "center" });
  });
  await wait(600);
  await shot(page, "spacex-demo-16x9-subscribe-endpoints.png");
  const fold = page
    .locator("button, summary, details, .fold-toggle")
    .filter({ hasText: /prompt|relay|AI|Endpoints/i })
    .first();
  if (await fold.count()) {
    await fold.click().catch(() => {});
    await wait(600);
    await shot(page, "spacex-demo-16x9-subscribe-prompt.png");
  }

  // Full sky reset
  const reset = page
    .locator(".sky-reset:not([hidden]), button:has-text('Back to live'), button:has-text('Full sky')")
    .first();
  if (await reset.count()) {
    await reset.click();
    await wait(1500);
    await shot(page, "spacex-demo-16x9-fullsky-reset.png");
  }

  // Betelgeuse / galactic
  const bet = page
    .locator("button.event-card, button.scenario-card, .event-card, button")
    .filter({ hasText: /Betelgeuse|Galactic|CCSN/i })
    .first();
  if (await bet.count()) {
    await bet.click();
    await wait(7000);
    await shot(page, "spacex-demo-16x9-betelgeuse.png");
    const row2 = page.locator(".obj-row, tr.candidate, .candidate-row").first();
    if (await row2.count()) {
      await row2.click();
      await wait(1500);
    }
    await shot(page, "spacex-demo-16x9-betelgeuse-ranked.png");
  }

  await browser.close();
  console.log("done");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
