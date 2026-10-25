/**
 * Record SpaceX-track usage walkthrough (1920×1080) from production.
 * Usage: node presentation/spacex/capture_walkthrough.mjs
 */
import { chromium } from "playwright";
import { mkdir, copyFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";
import fs from "node:fs";

const BASE = process.env.DEMO_BASE_URL || "https://supernova.lylinks.com/spacex";
const OUT = process.env.DEMO_OUT || "/opt/cursor/artifacts/presentation";
const VIDEO_DIR = "/tmp/spacex-walkthrough-video";
const VIEWPORT = { width: 1920, height: 1080 };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  await mkdir(OUT, { recursive: true });
  fs.rmSync(VIDEO_DIR, { recursive: true, force: true });
  await mkdir(VIDEO_DIR, { recursive: true });

  const browser = await chromium.launch({
    headless: true,
    executablePath: "/usr/local/bin/google-chrome",
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 1,
    recordVideo: { dir: VIDEO_DIR, size: VIEWPORT },
  });
  const page = await context.newPage();
  page.setDefaultTimeout(90_000);

  await page.goto(BASE + "/", { waitUntil: "networkidle", timeout: 90_000 });
  await wait(2000);

  // About
  const about = page.locator("a.nav-about").first();
  if (await about.count()) {
    await about.click();
    await wait(2200);
  }
  const back = page.locator("#brand-link, a.about-back, button:has-text('Back')").first();
  if (await back.count()) await back.click();
  else await page.goto(BASE + "/", { waitUntil: "networkidle" });
  await wait(1000);

  // IceCube
  const ice = page
    .locator("button.event-card, button.scenario-card, button")
    .filter({ hasText: /IceCube/i })
    .first();
  if (await ice.count()) {
    await ice.click();
    await wait(6000);
  }
  const row = page.locator(".obj-row").first();
  if (await row.count()) {
    await row.click();
    await wait(2000);
  }

  // scroll subscribe
  await page.evaluate(() => {
    const el = document.querySelector("#panel-subscribe") || document.querySelector(".subscribe-panel");
    if (el) el.scrollIntoView({ block: "center" });
  });
  await wait(2000);

  // reset
  const reset = page.locator(".sky-reset:not([hidden]), button:has-text('Back to live')").first();
  if (await reset.count()) {
    await reset.click();
    await wait(2500);
  }

  await context.close();
  await browser.close();

  // find webm
  const files = fs.readdirSync(VIDEO_DIR).filter((f) => f.endsWith(".webm"));
  if (!files.length) throw new Error("no webm recorded");
  const webm = path.join(VIDEO_DIR, files[0]);
  const destWebm = path.join(OUT, "spacex-demo-usage-walkthrough.webm");
  const destMp4 = path.join(OUT, "spacex-demo-usage-walkthrough.mp4");
  await copyFile(webm, destWebm);

  await new Promise((resolve, reject) => {
    const ff = spawn(
      "ffmpeg",
      ["-y", "-i", webm, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", destMp4],
      { stdio: "inherit" },
    );
    ff.on("exit", (code) => (code === 0 ? resolve() : reject(new Error("ffmpeg " + code))));
  });
  console.log("saved", destMp4);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
