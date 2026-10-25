/**
 * Interactive skymap: real DSS/HiPS via Aladin Lite when online, with
 * zoom-to-region + red 90% outline + hoverable ranked stars.
 * Offline fallback: focus PNG + SVG overlay (same outline + hover).
 */
import strings from "../copy/strings.json";
import {
  getState,
  selectStar,
  subscribe,
  type CandidateRow,
  type SkymapPayload,
} from "../state/store";
import {
  loadAladin,
  type AladinApi,
  type AladinInstance,
  type Catalog,
  type CatalogSource,
  type GraphicOverlay,
} from "../sky/aladin";
import { raDecToFocusPx } from "../sky/projection";

export type RegionPayload = {
  alert_id: string;
  peak: { ra_deg: number; dec_deg: number };
  fov_deg: number;
  credible_deg2: number;
  outline: number[][];
  simulated: boolean;
  survey_hint?: string;
};

type HoverInfo = {
  rank: number;
  star_id: string;
  class: string;
  posterior: number;
  p_sky: number;
  ra_deg: number;
  dec_deg: number;
  simulated: boolean;
};

async function fetchRegion(alertId: string): Promise<RegionPayload | null> {
  try {
    const res = await fetch(
      `/api/skymap/${encodeURIComponent(alertId)}/region`,
      { cache: "no-store" },
    );
    if (!res.ok) return null;
    return (await res.json()) as RegionPayload;
  } catch {
    return null;
  }
}

function formatHover(info: HoverInfo): string {
  const post = (info.posterior * 100).toFixed(1);
  const psky = (info.p_sky * 100).toFixed(2);
  const sim = info.simulated ? ` · ${strings.simulatedBadge}` : "";
  return (
    `#${info.rank} ${info.star_id} · ${info.class}${sim}\n` +
    `${strings.skyHoverPosterior}: ${post}% · ${strings.skyHoverPSky}: ${psky}%\n` +
    `RA ${info.ra_deg.toFixed(3)}° · Dec ${info.dec_deg.toFixed(3)}°`
  );
}

function candidateHover(
  row: CandidateRow,
  rank: number,
): HoverInfo {
  return {
    rank,
    star_id: row.star_id,
    class: row.class,
    posterior: row.posterior,
    p_sky: row.p_sky,
    ra_deg: row.ra_deg,
    dec_deg: row.dec_deg,
    simulated: Boolean(row.simulated),
  };
}

export function mountSky(host: HTMLElement): () => void {
  host.innerHTML = `
    <div class="sky-stage" data-role="stage">
      <div class="sky-empty" data-role="empty">${strings.skyEmpty}</div>
      <div class="sky-aladin" data-role="aladin" hidden></div>
      <div class="sky-fallback" data-role="fallback" hidden>
        <img class="sky-img" data-role="focus-img" alt="${strings.skyTitle}" />
        <svg class="sky-overlay" data-role="overlay" aria-hidden="true"></svg>
      </div>
      <div class="sky-hover" data-role="hover" hidden></div>
      <div class="sky-meta" data-role="meta" hidden></div>
    </div>
  `;

  const empty = host.querySelector<HTMLElement>("[data-role=empty]")!;
  const aladinHost = host.querySelector<HTMLElement>("[data-role=aladin]")!;
  const fallback = host.querySelector<HTMLElement>("[data-role=fallback]")!;
  const focusImg = host.querySelector<HTMLImageElement>("[data-role=focus-img]")!;
  const overlay = host.querySelector<SVGSVGElement>("[data-role=overlay]")!;
  const hoverEl = host.querySelector<HTMLElement>("[data-role=hover]")!;
  const meta = host.querySelector<HTMLElement>("[data-role=meta]")!;

  let lastAlertId: string | null = null;
  let region: RegionPayload | null = null;
  let mode: "aladin" | "fallback" | null = null;
  let Aref: AladinApi | null = null;
  let aladin: AladinInstance | null = null;
  let overlayLayer: GraphicOverlay | null = null;
  let catalog: Catalog | null = null;
  let renderSeq = 0;
  let aladinHoverBound = false;

  const showHover = (info: HoverInfo | null, clientX?: number, clientY?: number) => {
    if (!info) {
      hoverEl.hidden = true;
      hoverEl.textContent = "";
      return;
    }
    hoverEl.hidden = false;
    hoverEl.textContent = formatHover(info);
    if (clientX != null && clientY != null) {
      const rect = host.getBoundingClientRect();
      const x = Math.min(clientX - rect.left + 12, rect.width - 220);
      const y = Math.min(clientY - rect.top + 12, rect.height - 90);
      hoverEl.style.left = `${Math.max(8, x)}px`;
      hoverEl.style.top = `${Math.max(8, y)}px`;
    }
  };

  const setMeta = (skymap: SkymapPayload, reg: RegionPayload | null) => {
    meta.hidden = false;
    const peak = reg?.peak ?? skymap.peak;
    const area = reg?.credible_deg2 ?? skymap.credible_90_deg2;
    const fov = reg?.fov_deg;
    meta.innerHTML = `
      <span>${strings.skyPeak} RA ${peak.ra_deg.toFixed(2)}° · Dec ${peak.dec_deg.toFixed(2)}°</span>
      <span>90% · ${area.toFixed(1)} deg²${fov ? ` · FoV ${fov.toFixed(1)}°` : ""}</span>
      <span class="sky-mode">${mode === "aladin" ? strings.skyModeLive : strings.skyModeFocus}</span>
      ${(reg?.simulated ?? skymap.simulated)
        ? `<span class="badge sim">${strings.simulatedBadge}</span>`
        : `<span class="badge real">${strings.realBadge}</span>`}
    `;
  };

  const drawFallbackOverlay = (
    reg: RegionPayload,
    candidates: CandidateRow[],
  ) => {
    const w = focusImg.clientWidth || fallback.clientWidth || 640;
    const h = focusImg.clientHeight || Math.round(w * 0.85) || 480;
    overlay.setAttribute("viewBox", `0 0 ${w} ${h}`);
    overlay.setAttribute("width", String(w));
    overlay.setAttribute("height", String(h));
    overlay.innerHTML = "";

    const peak = reg.peak;
    const fov = reg.fov_deg;

    // Red credible-region outline
    const pts: string[] = [];
    for (const pair of reg.outline) {
      const ra = Number(pair[0]);
      const dec = Number(pair[1]);
      const p = raDecToFocusPx(ra, dec, peak.ra_deg, peak.dec_deg, fov, w, h);
      if (p) pts.push(`${p.x.toFixed(1)},${p.y.toFixed(1)}`);
    }
    if (pts.length >= 2) {
      const poly = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      poly.setAttribute("points", pts.join(" "));
      poly.setAttribute("class", "sky-outline");
      overlay.appendChild(poly);
    }

    candidates.forEach((row, idx) => {
      const p = raDecToFocusPx(
        row.ra_deg,
        row.dec_deg,
        peak.ra_deg,
        peak.dec_deg,
        fov,
        w,
        h,
      );
      if (!p) return;
      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", "sky-star");
      g.style.cursor = "pointer";
      const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("cx", String(p.x));
      c.setAttribute("cy", String(p.y));
      c.setAttribute("r", idx === 0 ? "7" : "5");
      const info = candidateHover(row, idx + 1);
      g.addEventListener("pointerenter", (ev) => {
        showHover(info, ev.clientX, ev.clientY);
        selectStar(row.star_id);
      });
      g.addEventListener("pointermove", (ev) => showHover(info, ev.clientX, ev.clientY));
      g.addEventListener("pointerleave", () => showHover(null));
      g.addEventListener("click", () => selectStar(row.star_id));
      g.appendChild(c);
      overlay.appendChild(g);
    });
  };

  const syncAladin = (reg: RegionPayload, candidates: CandidateRow[]) => {
    if (!aladin || !Aref) return;
    aladin.gotoRaDec(reg.peak.ra_deg, reg.peak.dec_deg);
    aladin.setFov(reg.fov_deg);
    aladin.removeLayers();

    overlayLayer = Aref.graphicOverlay({ color: "#e23b3b", lineWidth: 3 });
    aladin.addOverlay(overlayLayer);
    if (reg.outline.length >= 3) {
      overlayLayer.addFootprints([
        Aref.polygon(reg.outline.map((p) => [Number(p[0]), Number(p[1])]), {
          color: "#e23b3b",
          lineWidth: 3,
        }),
      ]);
    }

    catalog = Aref.catalog({
      name: "BREAKOUT ranked",
      color: "#1ec8b2",
      sourceSize: 14,
      shape: "circle",
      hoverColor: "#ffd166",
      displayLabel: true,
      labelColumn: "label",
      labelColor: "#eef3f7",
      labelFont: "11px IBM Plex Sans, sans-serif",
      onClick: "showPopup",
    });
    aladin.addCatalog(catalog);

    const sources = candidates.map((row, idx) => {
      const info = candidateHover(row, idx + 1);
      return Aref!.source(row.ra_deg, row.dec_deg, {
        name: row.star_id,
        label: `#${info.rank}`,
        rank: info.rank,
        star_id: info.star_id,
        class: info.class,
        posterior: info.posterior,
        p_sky: info.p_sky,
        simulated: info.simulated,
        popupTitle: `#${info.rank} ${info.star_id}`,
        popupDesc: formatHover(info).replaceAll("\n", "<br/>"),
      });
    });
    catalog.addSources(sources);

    if (!aladinHoverBound) {
      aladinHoverBound = true;
      aladin.on("objectHovered", (obj: CatalogSource | null) => {
        if (!obj?.data) {
          showHover(null);
          return;
        }
        const d = obj.data;
        showHover({
          rank: Number(d.rank) || 0,
          star_id: String(d.star_id ?? d.name ?? ""),
          class: String(d.class ?? ""),
          posterior: Number(d.posterior) || 0,
          p_sky: Number(d.p_sky) || 0,
          ra_deg: Number(obj.ra) || 0,
          dec_deg: Number(obj.dec) || 0,
          simulated: Boolean(d.simulated),
        });
        if (d.star_id) selectStar(String(d.star_id));
      });
    }
  };

  const useFallback = async (
    skymap: SkymapPayload,
    reg: RegionPayload,
    candidates: CandidateRow[],
  ) => {
    mode = "fallback";
    aladinHost.hidden = true;
    fallback.hidden = false;
    empty.hidden = true;
    const src = `/api/skymap/${encodeURIComponent(skymap.alert_id)}/focus.png?v=${encodeURIComponent(skymap.alert_id)}`;
    await new Promise<void>((resolve) => {
      focusImg.onload = () => resolve();
      focusImg.onerror = () => resolve();
      if (focusImg.getAttribute("src") !== src) focusImg.src = src;
      else if (focusImg.complete) resolve();
    });
    focusImg.classList.add("is-in");
    drawFallbackOverlay(reg, candidates);
    setMeta(skymap, reg);
  };

  const useAladin = async (
    skymap: SkymapPayload,
    reg: RegionPayload,
    candidates: CandidateRow[],
  ) => {
    if (!Aref) Aref = await loadAladin();
    empty.hidden = true;
    // Keep Aladin hidden until a canvas appears so failures never cover the focus map.
    aladinHost.hidden = true;
    if (!aladin) {
      aladinHost.innerHTML = "";
      try {
        aladin = Aref.aladin(aladinHost, {
          survey: reg.survey_hint || "P/DSS2/color",
          fov: reg.fov_deg,
          target: `${reg.peak.ra_deg} ${reg.peak.dec_deg}`,
          cooFrame: "ICRSd",
          showReticle: false,
          showCooGrid: true,
          showCooGridControl: false,
          showProjectionControl: false,
          showFullscreenControl: false,
          showLayersControl: false,
          showGotoControl: false,
          showShareControl: false,
          showFrame: true,
          showSimbadPointerControl: false,
        });
      } catch (err) {
        aladin = null;
        aladinHost.hidden = true;
        aladinHost.innerHTML = "";
        throw err;
      }
    }
    await new Promise((r) => window.setTimeout(r, 700));
    if (!aladinHost.querySelector("canvas")) {
      try {
        aladin?.destroy?.();
      } catch {
        /* ignore */
      }
      aladin = null;
      aladinHoverBound = false;
      aladinHost.hidden = true;
      aladinHost.innerHTML = "";
      throw new Error("Aladin produced no canvas");
    }
    syncAladin(reg, candidates);
    mode = "aladin";
    fallback.hidden = true;
    aladinHost.hidden = false;
    setMeta(skymap, reg);
  };

  const render = async () => {
    const seq = ++renderSeq;
    const { skymap, candidates } = getState();
    if (!skymap) {
      empty.hidden = false;
      aladinHost.hidden = true;
      fallback.hidden = true;
      meta.hidden = true;
      showHover(null);
      lastAlertId = null;
      region = null;
      return;
    }

    empty.hidden = true;
    if (skymap.alert_id !== lastAlertId || !region) {
      lastAlertId = skymap.alert_id;
      region = await fetchRegion(skymap.alert_id);
      if (seq !== renderSeq) return;
    }
    if (!region) {
      // Last-resort: static mollweide if region API fails
      mode = "fallback";
      aladinHost.hidden = true;
      fallback.hidden = false;
      focusImg.src = `/api/skymap/${encodeURIComponent(skymap.alert_id)}/png?v=${encodeURIComponent(skymap.alert_id)}`;
      setMeta(skymap, null);
      return;
    }

    // Always paint the focus map first (zoom + red outline + hover).
    // Upgrade to Aladin DSS/HiPS only when it actually produces a canvas.
    await useFallback(skymap, region, candidates);
    if (seq !== renderSeq) return;
    try {
      await useAladin(skymap, region, candidates);
    } catch {
      if (seq !== renderSeq) return;
      await useFallback(skymap, region, candidates);
    }
  };

  const unsub = subscribe(() => {
    void render();
  });
  const onResize = () => {
    if (mode === "fallback" && region) {
      drawFallbackOverlay(region, getState().candidates);
    }
  };
  window.addEventListener("resize", onResize);

  return () => {
    unsub();
    window.removeEventListener("resize", onResize);
    try {
      aladin?.destroy?.();
    } catch {
      /* ignore */
    }
  };
}
