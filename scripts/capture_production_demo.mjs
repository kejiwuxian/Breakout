/**
 * Capture 16:9 production screenshots + usage walkthrough video
 * against https://supernova.lylinks.com
 *
 * Usage: node scripts/capture_production_demo.mjs
 */
import { chromium } from "playwright";
import { mkdir, copyFile, access } from "node:fs/promises";
import path from "node:path";

const BASE = process.env.DEMO_BASE_URL || "https://supernova.lylinks.com";
const OUT = process.env.DEMO_OUT || "/opt/cursor/artifacts";
const VIEWPORT = { width: 1920, height: 1080 };
const VIDEO_DIR = "/tmp/supernova-demo-video";

async function wait(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function shot(page, name) {
  const dest = path.join(OUT, name);
  await page.screenshot({ path: dest, fullPage: false });
  console.log("saved", dest);
  return dest;
}

async function waitForCandidates(page, timeout = 90_000) {
  await page.waitForSelector(".obj-row", { timeout });
}

async function waitForZoomed(page, timeout = 60_000) {
  // Reset button appears when zoomed into AOI
  try {
    await page.waitForSelector(".sky-reset:not([hidden])", { timeout });
    return true;
  } catch {
    return false;
  }
}

async function main() {
  await mkdir(OUT, { recursive: true });
  await mkdir(VIDEO_DIR, { recursive: true });

  const browser = await chromium.launch({
    headless: true,
    args: ["--disable-dev-shm-usage"],
  });

  // —— Stills pass ——
  {
    const context = await browser.newContext({
      viewport: VIEWPORT,
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    page.setDefaultTimeout(90_000);

    console.log("Opening", BASE);
    await page.goto(BASE + "/", { waitUntil: "networkidle" });
    await page.waitForSelector(".brand");
    await page.waitForSelector(".sky-stage, #panel-sky svg, .sky-host", {
      timeout: 60_000,
    });
    // Let BSC5 field paint
    await wait(2500);
    await shot(page, "demo-16x9-idle.png");

    // About
    await page.click("#nav-about");
    await page.waitForSelector(".about-heading");
    await wait(600);
    await shot(page, "demo-16x9-about.png");

    // Back to mission — event cards visible
    await page.click("#brand-link");
    await page.waitForSelector("#mission-view:not([hidden])");
    await page.waitForSelector(".event-card");
    await wait(500);
    await shot(page, "demo-16x9-event-cards.png");

    // IceCube replay
    await page.click('button[data-scenario="scenario_b_icecube_170922a"]');
    await waitForCandidates(page);
    const zoomedIce = await waitForZoomed(page);
    await wait(1500);
    await shot(page, "demo-16x9-icecube.png");
    if (zoomedIce) {
      await shot(page, "demo-16x9-icecube-aoi-zoom.png");
    }

    // Select first candidate (detail + life/breakout/composition)
    const firstRow = page.locator(".obj-row").first();
    await firstRow.click();
    await wait(800);
    // Scroll rail so detail is visible if needed
    await page.locator(".rail").evaluate((el) => {
      el.scrollTop = 0;
    });
    await wait(400);
    await shot(page, "demo-16x9-candidate-selected.png");

    // Subscribe / Endpoints — expand AI prompt
    const subscribe = page.locator(".subscribe");
    await subscribe.scrollIntoViewIfNeeded();
    await wait(400);
    const relay = page.locator("details.subscribe-relay");
    if (await relay.count()) {
      await relay.evaluate((el) => {
        el.open = true;
      });
      await wait(400);
    }
    await shot(page, "demo-16x9-subscribe-endpoints.png");

    // Full sky / zoom reset
    const reset = page.locator(".sky-reset:not([hidden])");
    if (await reset.count()) {
      await reset.click();
      await wait(1200);
      await shot(page, "demo-16x9-fullsky-reset.png");
    }

    // Betelgeuse / galactic CCSN
    await page.click('button[data-scenario="scenario_a_galactic_ccsn"]');
    await waitForCandidates(page);
    await waitForZoomed(page);
    await wait(1500);
    await shot(page, "demo-16x9-betelgeuse.png");

    await context.close();
  }

  // —— Walkthrough video ——
  {
    const context = await browser.newContext({
      viewport: VIEWPORT,
      deviceScaleFactor: 1,
      recordVideo: {
        dir: VIDEO_DIR,
        size: VIEWPORT,
      },
    });
    const page = await context.newPage();
    page.setDefaultTimeout(90_000);

    await page.goto(BASE + "/", { waitUntil: "networkidle" });
    await page.waitForSelector(".brand");
    await wait(1800);

    // About → back
    await page.click("#nav-about");
    await page.waitForSelector(".about-heading");
    await wait(1400);
    await page.click("[data-role='about-back']");
    await page.waitForSelector("#mission-view:not([hidden])");
    await wait(900);

    // IceCube → AOI zoom
    await page.click('button[data-scenario="scenario_b_icecube_170922a"]');
    await waitForCandidates(page);
    await waitForZoomed(page);
    await wait(2200);

    // Select candidate
    await page.locator(".obj-row").first().click();
    await wait(1400);

    // Subscribe glance
    await page.locator(".subscribe").scrollIntoViewIfNeeded();
    await wait(700);
    const relay = page.locator("details.subscribe-relay");
    if (await relay.count()) {
      await relay.evaluate((el) => {
        el.open = true;
      });
      await wait(900);
    }

    // Zoom out / reset
    await page.locator(".rail").evaluate((el) => {
      el.scrollTop = 0;
    });
    await wait(400);
    const reset = page.locator(".sky-reset:not([hidden])");
    if (await reset.count()) {
      await reset.click();
      await wait(1800);
    } else {
      // Wheel zoom out as fallback
      const sky = page.locator(".sky-stage, #panel-sky");
      const box = await sky.boundingBox();
      if (box) {
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await page.mouse.wheel(0, -900);
        await wait(1000);
      }
    }

    await wait(800);
    await context.close();

    // Find the recorded webm and convert/copy to artifacts
    const { readdir } = await import("node:fs/promises");
    const files = (await readdir(VIDEO_DIR)).filter((f) => f.endsWith(".webm"));
    if (!files.length) throw new Error("No video recorded");
    const webmPath = path.join(VIDEO_DIR, files[0]);
    const outWebm = path.join(OUT, "demo-usage-walkthrough.webm");
    const outMp4 = path.join(OUT, "demo-usage-walkthrough.mp4");
    await copyFile(webmPath, outWebm);
    console.log("saved", outWebm);

    // Prefer mp4 via ffmpeg when available
    const { spawnSync } = await import("node:child_process");
    const ff = spawnSync(
      "ffmpeg",
      [
        "-y",
        "-i",
        webmPath,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        outMp4,
      ],
      { encoding: "utf8" },
    );
    if (ff.status === 0) {
      console.log("saved", outMp4);
    } else {
      console.warn("ffmpeg mp4 convert failed; webm kept.", ff.stderr?.slice(-400));
    }
  }

  await browser.close();
  console.log("done");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
