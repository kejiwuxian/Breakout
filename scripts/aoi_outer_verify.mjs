/**
 * IceCube AOI verification: outer mark translucent, inner opaque, ranked star count.
 * Writes artifacts under /opt/cursor/artifacts/.
 */
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const OUT = "/opt/cursor/artifacts";
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
const log = [];

page.on("console", (msg) => {
  if (msg.type() === "error") log.push(`console.error: ${msg.text()}`);
});
page.on("pageerror", (err) => log.push(`pageerror: ${err}`));

await page.goto("http://127.0.0.1:5174/", { waitUntil: "networkidle" });
await page.waitForSelector(".brand, h1, [data-panel]", { timeout: 30_000 }).catch(() => {});

const startBtn = page.locator('button[data-scenario="scenario_b_icecube_170922a"]');
await startBtn.waitFor({ state: "visible", timeout: 30_000 });
await startBtn.click();

// Wait for ranked AOI stars + dual marks with settled geometry-based roles
// (IceCube: peak ring larger → outer/translucent; ellipse → inner/opaque).
await page.waitForFunction(
  () => {
    const stars = document.querySelectorAll(".sky-star");
    const outline = document.querySelector(".sky-outline");
    const peak = document.querySelector(".sky-outline-peak");
    if (stars.length < 3 || !outline || !peak) return false;
    const cx = Number(peak.getAttribute("cx"));
    const cy = Number(peak.getAttribute("cy"));
    const peakR = Number(peak.getAttribute("r"));
    if (!Number.isFinite(cx) || !Number.isFinite(peakR)) return false;
    let ovalR = 0;
    for (const t of (outline.getAttribute("points") || "").trim().split(/\s+/)) {
      const [x, y] = t.split(",").map(Number);
      if (Number.isFinite(x) && Number.isFinite(y)) {
        ovalR = Math.max(ovalR, Math.hypot(x - cx, y - cy));
      }
    }
    // IceCube: peak ring must be the larger mark and marked outer.
    return (
      peakR > ovalR &&
      peak.getAttribute("data-aoi-role") === "outer" &&
      outline.getAttribute("data-aoi-role") === "inner"
    );
  },
  { timeout: 90_000 },
);
await page.waitForTimeout(400);

const metrics = await page.evaluate(() => {
  const outline = document.querySelector(".sky-outline");
  const peak = document.querySelector(".sky-outline-peak");
  const cs = (el) => {
    if (!el) return null;
    const s = getComputedStyle(el);
    return {
      class: el.getAttribute("class"),
      role: el.getAttribute("data-aoi-role"),
      // Prefer computed style — presentation attrs can be overridden by CSS.
      stroke: s.stroke,
      strokeOpacity: s.strokeOpacity,
      fill: s.fill,
      inlineStroke: el.style?.stroke || null,
      r: el.getAttribute("r"),
    };
  };
  const o = cs(outline);
  const p = cs(peak);
  // Projected sizes from geometry attributes
  let ovalR = 0;
  if (outline) {
    const pts = (outline.getAttribute("points") || "").trim().split(/\s+/);
    const peakEl = peak;
    const cx = peakEl ? Number(peakEl.getAttribute("cx")) : 0;
    const cy = peakEl ? Number(peakEl.getAttribute("cy")) : 0;
    for (const t of pts) {
      const [x, y] = t.split(",").map(Number);
      if (Number.isFinite(x) && Number.isFinite(y)) {
        ovalR = Math.max(ovalR, Math.hypot(x - cx, y - cy));
      }
    }
  }
  const peakR = peak ? Number(peak.getAttribute("r")) : 0;
  return {
    nRankedStars: document.querySelectorAll(".sky-star").length,
    outline: o,
    peak: p,
    ovalR,
    peakR,
    outerIsPeak: peakR > ovalR,
  };
});

fs.writeFileSync(
  path.join(OUT, "icecube_aoi_metrics.json"),
  JSON.stringify({ metrics, log }, null, 2),
);

await page.locator("svg.sky-svg, .sky-panel svg, svg").first().screenshot({
  path: path.join(OUT, "icecube_outer_translucent_inner_opaque.png"),
});
await page.screenshot({
  path: path.join(OUT, "icecube_aoi_full_dashboard.png"),
  fullPage: false,
});

console.log(JSON.stringify({ metrics, log }, null, 2));

const peakStroke = String(metrics.peak?.stroke || "");
const ovalStroke = String(metrics.outline?.stroke || "");
const peakTranslucent =
  peakStroke.includes("0.4") ||
  Number(metrics.peak?.strokeOpacity) < 0.95 ||
  String(metrics.peak?.inlineStroke || "").includes("0.4");
const ovalOpaque =
  !ovalStroke.includes("0.4") &&
  (ovalStroke.includes("255, 0, 0") ||
    ovalStroke.includes("rgb(255, 0, 0)") ||
    ovalStroke === "#ff0000" ||
    String(metrics.outline?.inlineStroke || "") === "#ff0000");

const ok =
  metrics.nRankedStars >= 3 &&
  metrics.outerIsPeak &&
  metrics.outline?.role === "inner" &&
  metrics.peak?.role === "outer" &&
  peakTranslucent &&
  ovalOpaque;

await browser.close();
if (!ok) {
  console.error("VERIFICATION_FAILED", { metrics, peakTranslucent, ovalOpaque });
  process.exit(1);
}
console.log("VERIFICATION_OK");
