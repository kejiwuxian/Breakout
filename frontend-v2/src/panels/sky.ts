/**
 * Full-sky Mollweide by default. On a neutrino event: draw a smooth red oval
 * from the localization ellipse, animate a zoom toward the peak, then settle
 * on the focus map for accurate star hover (rank / posterior / p_sky).
 */
import strings from "../copy/strings.json";
import {
  clearSkyZoomSuppress,
  getState,
  selectStar,
  subscribe,
  type CandidateRow,
  type SkymapPayload,
} from "../state/store";
import { raDecToFocusPx } from "../sky/projection";
import { raDecToMollweide } from "../sky/mollweide";

export type EllipsePayload = {
  ra_deg: number;
  dec_deg: number;
  semi_major_deg: number;
  semi_minor_deg: number;
  pa_deg: number;
  area_deg2: number;
};

export type RegionPayload = {
  alert_id: string;
  peak: { ra_deg: number; dec_deg: number };
  fov_deg: number;
  credible_deg2: number;
  outline: number[][];
  ellipse?: EllipsePayload;
  shape?: string;
  simulated: boolean;
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

type ViewMode = "full" | "zooming" | "focus";

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

function candidateHover(row: CandidateRow, rank: number): HoverInfo {
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

function ellipseOutline(ell: EllipsePayload, n = 96): number[][] {
  const ra0 = ell.ra_deg;
  const dec0 = ell.dec_deg;
  const a = ell.semi_major_deg;
  const b = ell.semi_minor_deg;
  const pa = (ell.pa_deg * Math.PI) / 180;
  const cosd = Math.max(Math.cos((dec0 * Math.PI) / 180), 0.15);
  const ring: number[][] = [];
  for (let i = 0; i < n; i++) {
    const t = (2 * Math.PI * i) / n;
    const dm = a * Math.cos(t);
    const dn = b * Math.sin(t);
    const east = dm * Math.sin(pa) + dn * Math.cos(pa);
    const north = dm * Math.cos(pa) - dn * Math.sin(pa);
    const ra = (((ra0 + east / cosd) % 360) + 360) % 360;
    const dec = Math.max(-90, Math.min(90, dec0 + north));
    ring.push([ra, dec]);
  }
  ring.push(ring[0]!);
  return ring;
}

function outlineRing(reg: RegionPayload): number[][] {
  if (reg.outline?.length >= 4) return reg.outline;
  if (reg.ellipse) return ellipseOutline(reg.ellipse);
  return [];
}

function loadImage(img: HTMLImageElement, src: string): Promise<void> {
  return new Promise((resolve) => {
    img.onload = () => resolve();
    img.onerror = () => resolve();
    if (img.getAttribute("src") !== src) {
      img.src = src;
    } else if (img.complete) {
      resolve();
    }
  });
}

export function mountSky(host: HTMLElement): () => void {
  host.innerHTML = `
    <div class="sky-stage" data-role="stage">
      <div class="sky-empty" data-role="empty">${strings.skyEmpty}</div>
      <div class="sky-world" data-role="world" hidden>
        <div class="sky-zoomable" data-role="zoomable">
          <div class="sky-frame" data-role="frame">
            <img class="sky-img sky-full" data-role="full-img" alt="${strings.skyTitle}" />
            <img class="sky-img sky-focus" data-role="focus-img" alt="" hidden />
            <svg class="sky-overlay" data-role="overlay" aria-hidden="true"></svg>
          </div>
        </div>
      </div>
      <div class="sky-hover" data-role="hover" hidden></div>
      <div class="sky-meta" data-role="meta" hidden></div>
    </div>
  `;

  const empty = host.querySelector<HTMLElement>("[data-role=empty]")!;
  const world = host.querySelector<HTMLElement>("[data-role=world]")!;
  const zoomable = host.querySelector<HTMLElement>("[data-role=zoomable]")!;
  const frame = host.querySelector<HTMLElement>("[data-role=frame]")!;
  const full = host.querySelector<HTMLImageElement>("[data-role=full-img]")!;
  const focus = host.querySelector<HTMLImageElement>("[data-role=focus-img]")!;
  const overlay = host.querySelector<SVGSVGElement>("[data-role=overlay]")!;
  const hoverEl = host.querySelector<HTMLElement>("[data-role=hover]")!;
  const meta = host.querySelector<HTMLElement>("[data-role=meta]")!;

  let region: RegionPayload | null = null;
  /** Alert id we already played the zoom sequence for (survives render races). */
  let animatedAlertId: string | null = null;
  let seenZoomNonce = 0;
  let renderSeq = 0;
  let viewMode: ViewMode = "full";
  let zoomTimer = 0;
  let settleTimer = 0;

  /** Fit the map stack to the stage using the active image's intrinsic aspect. */
  const fitFrame = (img: HTMLImageElement) => {
    const ar =
      img.naturalWidth > 0 && img.naturalHeight > 0
        ? img.naturalWidth / img.naturalHeight
        : 2;
    const pw = world.clientWidth || host.clientWidth || 640;
    const ph = world.clientHeight || host.clientHeight || 360;
    let w = pw;
    let h = w / ar;
    if (h > ph) {
      h = ph;
      w = h * ar;
    }
    frame.style.width = `${Math.max(1, Math.floor(w))}px`;
    frame.style.height = `${Math.max(1, Math.floor(h))}px`;
    return { w: frame.clientWidth || w, h: frame.clientHeight || h, ar };
  };

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

  const phaseLabel = () => {
    if (viewMode === "full") return strings.skyModeFull;
    if (viewMode === "zooming") return strings.skyModeZoom;
    return strings.skyModeFocus;
  };

  const setMeta = (skymap: SkymapPayload, reg: RegionPayload | null) => {
    meta.hidden = false;
    const peak = reg?.peak ?? skymap.peak;
    const area = reg?.credible_deg2 ?? skymap.credible_90_deg2;
    const ell = reg?.ellipse;
    const axes = ell
      ? ` · oval ${ell.semi_major_deg.toFixed(1)}°×${ell.semi_minor_deg.toFixed(1)}°`
      : "";
    meta.innerHTML = `
      <span>${strings.skyPeak} RA ${peak.ra_deg.toFixed(2)}° · Dec ${peak.dec_deg.toFixed(2)}°</span>
      <span>90% · ${area.toFixed(1)} deg²${axes}</span>
      <span class="sky-mode">${phaseLabel()}</span>
      ${(reg?.simulated ?? skymap.simulated)
        ? `<span class="badge sim">${strings.simulatedBadge}</span>`
        : `<span class="badge real">${strings.realBadge}</span>`}
    `;
  };

  const wireStar = (g: SVGGElement, row: CandidateRow, rank: number) => {
    const info = candidateHover(row, rank);
    g.style.cursor = "pointer";
    g.addEventListener("pointerenter", (ev) => {
      showHover(info, ev.clientX, ev.clientY);
      selectStar(row.star_id);
    });
    g.addEventListener("pointermove", (ev) => showHover(info, ev.clientX, ev.clientY));
    g.addEventListener("pointerleave", () => showHover(null));
    g.addEventListener("click", () => selectStar(row.star_id));
  };

  const sizeOverlay = (w: number, h: number) => {
    overlay.setAttribute("viewBox", `0 0 ${w} ${h}`);
    overlay.setAttribute("width", String(w));
    overlay.setAttribute("height", String(h));
    overlay.innerHTML = "";
  };

  const drawOval = (
    pts: string[],
    opts: { strokeWidth: number },
  ) => {
    if (pts.length < 3) return;
    const poly = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
    poly.setAttribute("points", pts.join(" "));
    poly.setAttribute("class", "sky-outline");
    poly.setAttribute("stroke-width", String(opts.strokeWidth));
    overlay.appendChild(poly);
  };

  const drawFullOverlay = (reg: RegionPayload, candidates: CandidateRow[]) => {
    const { w, h } = fitFrame(full);
    sizeOverlay(w, h);

    const pts: string[] = [];
    for (const pair of outlineRing(reg)) {
      const p = raDecToMollweide(Number(pair[0]), Number(pair[1]), w, h);
      if (p) pts.push(`${p.x.toFixed(1)},${p.y.toFixed(1)}`);
    }
    drawOval(pts, { strokeWidth: 2.5 });

    candidates.forEach((row, idx) => {
      const p = raDecToMollweide(row.ra_deg, row.dec_deg, w, h);
      if (!p) return;
      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", "sky-star");
      const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("cx", String(p.x));
      c.setAttribute("cy", String(p.y));
      c.setAttribute("r", idx === 0 ? "6" : "4.5");
      g.appendChild(c);
      wireStar(g, row, idx + 1);
      overlay.appendChild(g);
    });
    return { w, h };
  };

  const drawFocusOverlay = (reg: RegionPayload, candidates: CandidateRow[]) => {
    const { w, h } = fitFrame(focus);
    sizeOverlay(w, h);

    const peak = reg.peak;
    const fov = reg.fov_deg;
    const pts: string[] = [];
    for (const pair of outlineRing(reg)) {
      const p = raDecToFocusPx(
        Number(pair[0]),
        Number(pair[1]),
        peak.ra_deg,
        peak.dec_deg,
        fov,
        w,
        h,
      );
      if (p) pts.push(`${p.x.toFixed(1)},${p.y.toFixed(1)}`);
    }
    drawOval(pts, { strokeWidth: 3 });

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
      const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("cx", String(p.x));
      c.setAttribute("cy", String(p.y));
      c.setAttribute("r", idx === 0 ? "7" : "5");
      g.appendChild(c);
      wireStar(g, row, idx + 1);
      overlay.appendChild(g);
    });
  };

  const clearFrameZoom = () => {
    // Drop scale without a reverse transition (otherwise settle animates back out).
    frame.style.transition = "none";
    frame.classList.remove("is-zoomed");
    frame.style.transform = "none";
    frame.style.transformOrigin = "50% 50%";
    void frame.offsetWidth;
    frame.style.transition = "";
  };

  const resetTransform = () => {
    clearFrameZoom();
    zoomable.classList.remove("is-focus");
    full.hidden = false;
    focus.hidden = true;
    focus.classList.remove("is-in");
  };

  const settleOnFocus = async (
    skymap: SkymapPayload,
    reg: RegionPayload,
    candidates: CandidateRow[],
  ) => {
    const src = `/api/skymap/${encodeURIComponent(skymap.alert_id)}/focus.png?v=${encodeURIComponent(skymap.alert_id)}`;
    await loadImage(focus, src);
    viewMode = "focus";
    clearFrameZoom();
    zoomable.classList.add("is-focus");
    full.hidden = true;
    full.classList.remove("is-in");
    focus.hidden = false;
    focus.classList.add("is-in");
    fitFrame(focus);
    drawFocusOverlay(reg, candidates);
    setMeta(skymap, reg);
  };

  const runZoomSequence = (
    skymap: SkymapPayload,
    reg: RegionPayload,
    candidates: CandidateRow[],
  ) => {
    const { w, h } = drawFullOverlay(reg, candidates);
    const pt = raDecToMollweide(reg.peak.ra_deg, reg.peak.dec_deg, w, h);
    const major = reg.ellipse?.semi_major_deg ?? Math.sqrt(reg.credible_deg2 / Math.PI);
    // Mollweide compresses longitude; use map width as ~360° across.
    const pxPerDeg = w / 360;
    const ovalPx = Math.max(major * pxPerDeg * 1.35, 10);
    const target = Math.min(w, h) * 0.62;
    const scale = Math.min(Math.max(target / ovalPx, 5), 20);

    viewMode = "full";
    resetTransform();
    full.classList.add("is-in");
    if (pt) {
      frame.style.transformOrigin = `${pt.x.toFixed(1)}px ${pt.y.toFixed(1)}px`;
    }
    setMeta(skymap, reg);

    window.clearTimeout(zoomTimer);
    window.clearTimeout(settleTimer);

    // Beat on full sky with oval visible, then zoom, then settle on focus map.
    zoomTimer = window.setTimeout(() => {
      viewMode = "zooming";
      setMeta(skymap, reg);
      // Double rAF so the browser commits transform-origin before scale.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          frame.classList.add("is-zoomed");
          frame.style.transform = `scale(${scale.toFixed(3)})`;
        });
      });
      settleTimer = window.setTimeout(() => {
        void settleOnFocus(skymap, reg, candidates);
      }, 1800);
    }, 800);
  };

  const showEvent = async (
    skymap: SkymapPayload,
    reg: RegionPayload,
    candidates: CandidateRow[],
    animate: boolean,
  ) => {
    empty.hidden = true;
    world.hidden = false;

    const fullSrc = `/api/skymap/${encodeURIComponent(skymap.alert_id)}/png?v=${encodeURIComponent(skymap.alert_id)}`;
    if (animate) full.classList.remove("is-in");
    await loadImage(full, fullSrc);
    fitFrame(full);

    if (animate) {
      // Wait one frame so the fitted frame has real layout boxes.
      requestAnimationFrame(() => {
        runZoomSequence(skymap, reg, candidates);
      });
      return;
    }

    // Candidate / store updates must not cancel an in-flight zoom sequence.
    if (viewMode === "zooming") return;
    if (viewMode === "focus") {
      await settleOnFocus(skymap, reg, candidates);
      return;
    }

    // Hydrate / resume: show full-sky Mollweide + oval without replaying zoom.
    viewMode = "full";
    resetTransform();
    full.classList.add("is-in");
    drawFullOverlay(reg, candidates);
    setMeta(skymap, reg);
  };

  const render = async () => {
    const seq = ++renderSeq;
    const { skymap, candidates, suppressSkyZoomOnce, skyZoomNonce } = getState();
    if (!skymap) {
      empty.hidden = false;
      world.hidden = true;
      meta.hidden = true;
      showHover(null);
      window.clearTimeout(zoomTimer);
      window.clearTimeout(settleTimer);
      resetTransform();
      viewMode = "full";
      animatedAlertId = null;
      region = null;
      return;
    }

    // Fetch region without claiming the alert as "shown" yet — otherwise a
    // concurrent render can see a stale flag and skip the zoom animation.
    if (!region || region.alert_id !== skymap.alert_id) {
      const next = await fetchRegion(skymap.alert_id);
      if (seq !== renderSeq) return;
      region = next;
    }
    if (!region) {
      empty.hidden = true;
      world.hidden = false;
      resetTransform();
      await loadImage(
        full,
        `/api/skymap/${encodeURIComponent(skymap.alert_id)}/png?v=${encodeURIComponent(skymap.alert_id)}`,
      );
      fitFrame(full);
      full.classList.add("is-in");
      setMeta(skymap, null);
      return;
    }

    if (skyZoomNonce !== seenZoomNonce) {
      seenZoomNonce = skyZoomNonce;
      animatedAlertId = null; // Scenario Run — replay zoom even if alert_id reused.
    }

    let shouldAnimate = skymap.alert_id !== animatedAlertId;
    if (suppressSkyZoomOnce) {
      shouldAnimate = false;
      animatedAlertId = skymap.alert_id;
      clearSkyZoomSuppress();
    } else if (shouldAnimate) {
      animatedAlertId = skymap.alert_id;
    }
    await showEvent(skymap, region, candidates, shouldAnimate);
  };

  const unsub = subscribe(() => {
    void render();
  });
  const onResize = () => {
    if (!region || world.hidden || !getState().skymap) return;
    if (viewMode === "focus") drawFocusOverlay(region, getState().candidates);
    else drawFullOverlay(region, getState().candidates);
  };
  window.addEventListener("resize", onResize);

  return () => {
    unsub();
    window.removeEventListener("resize", onResize);
    window.clearTimeout(zoomTimer);
    window.clearTimeout(settleTimer);
  };
}
