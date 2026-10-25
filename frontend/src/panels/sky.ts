/**
 * Pure-SVG Mollweide skymap. Public catalog stars + HEALPix
 * localization cells + smooth 90% oval. Zoom/pan is SVG viewBox camera —
 * no raster PNG swap, no CSS scale.
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
import { raDecToMollweide } from "../sky/mollweide";
import {
  createSvgEl,
  drawEquatorialGrid,
  mollweideLimbPath,
  projectRing,
} from "../sky/svgMap";


/** Shared magnitude → radius/opacity for field stars and ranked AOI stars. */
export function starStyleFromVmag(vmag: number | null | undefined): {
  r: number;
  opacity: number;
} {
  const v =
    vmag != null && !Number.isNaN(Number(vmag)) ? Number(vmag) : 5.5;
  return {
    r: Math.max(0.55, Math.min(2.8, 2.35 - 0.28 * v)),
    opacity: Math.max(0.22, Math.min(0.9, 0.82 - 0.09 * v)),
  };
}

/**
 * Angular radius of the IceCube-scale peak ring — must match backend
 * ``PEAK_RING_AOI_RADIUS_DEG`` (outer AOI ranking floor).
 */
export const PEAK_RING_AOI_RADIUS_DEG = 4.5;
/** Draw peak ring when credible semi-major is below this (matches backend). */
export const PEAK_RING_MAJOR_THRESHOLD_DEG = 8;

/** Outer AOI: mint `--signal` at 75% transparent (alpha 0.25). */
const AOI_STROKE_OUTER = "rgba(91, 224, 197, 0.25)";
/** Inner AOI: mint `--signal` at 50% transparent (alpha 0.50). */
const AOI_STROKE_INNER = "rgba(91, 224, 197, 0.50)";

/** Projected SVG radius of the peak ring at ``(ra, dec)``. */
export function peakRingRadiusPx(
  raDeg: number,
  decDeg: number,
  width: number,
  height: number,
  radiusDeg = PEAK_RING_AOI_RADIUS_DEG,
): number | null {
  const center = raDecToMollweide(raDeg, decDeg, width, height);
  if (!center) return null;
  const edgeDec = Math.max(-90, Math.min(90, decDeg + radiusDeg));
  const edge = raDecToMollweide(raDeg, edgeDec, width, height);
  const projected = edge
    ? Math.hypot(edge.x - center.x, edge.y - center.y)
    : Math.min(width, height) * 0.022;
  return Math.max(10, projected);
}

/** Max distance from ``(cx, cy)`` to points in an SVG ``points`` string. */
export function projectedOutlineRadiusPx(
  points: string,
  cx: number,
  cy: number,
): number {
  let maxR = 0;
  for (const token of points.trim().split(/\s+/)) {
    if (!token) continue;
    const [xs, ys] = token.split(",");
    const x = Number(xs);
    const y = Number(ys);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    maxR = Math.max(maxR, Math.hypot(x - cx, y - cy));
  }
  return maxR;
}

/** Assign outer (more transparent) vs inner (less transparent) strokes by size. */
export function assignAoiStrokeBySize(
  marks: Array<{ el: Element; sizePx: number }>,
): void {
  if (marks.length === 0) return;
  let outerIdx = 0;
  for (let i = 1; i < marks.length; i++) {
    if (marks[i]!.sizePx > marks[outerIdx]!.sizePx) outerIdx = i;
  }
  marks.forEach((m, i) => {
    const outer = i === outerIdx;
    // Inline style beats stylesheet stroke so geometry wins over class names.
    const el = m.el as HTMLElement & SVGElement;
    el.setAttribute("fill", "none");
    el.setAttribute("data-aoi-role", outer ? "outer" : "inner");
    el.style.fill = "none";
    el.style.stroke = outer ? AOI_STROKE_OUTER : AOI_STROKE_INNER;
  });
}

export type EllipsePayload = {
  ra_deg: number;
  dec_deg: number;
  semi_major_deg: number;
  semi_minor_deg: number;
  pa_deg: number;
  area_deg2: number;
};

export type FieldStar = {
  star_id: string;
  common_name?: string | null;
  ra_deg: number;
  dec_deg: number;
  class?: string;
  vmag?: number | null;
  source?: string;
};

export type ProbCell = {
  prob: number;
  weight: number;
  corners: number[][];
};

export type NestedEllipse = {
  level: number;
  ellipse: EllipsePayload;
  outline: number[][];
};

export type RegionPayload = {
  alert_id: string;
  peak: { ra_deg: number; dec_deg: number };
  fov_deg: number;
  credible_deg2: number;
  outline: number[][];
  ellipse?: EllipsePayload;
  nested_ellipses?: NestedEllipse[];
  /** Backend outer ranking aperture (deg); optional on older payloads. */
  outer_aoi_radius_deg?: number;
  /** True when the UI draws the IceCube-scale peak ring. */
  peak_ring?: boolean;
  prob_cells?: ProbCell[];
  field_stars?: FieldStar[];
  galactic_plane?: number[][];
  shape?: string;
  render?: string;
  simulated: boolean;
};

/**
 * Angular radius of the outer AOI used for zoom + ranking — larger of the
 * credible semi-major and the peak-ring floor when the ellipse is IceCube-scale.
 */
export function outerAoiRadiusDeg(reg: RegionPayload): number {
  if (
    typeof reg.outer_aoi_radius_deg === "number" &&
    Number.isFinite(reg.outer_aoi_radius_deg) &&
    reg.outer_aoi_radius_deg > 0
  ) {
    return reg.outer_aoi_radius_deg;
  }
  const majors: number[] = [];
  const major = Number(reg.ellipse?.semi_major_deg ?? 0);
  if (Number.isFinite(major) && major > 0) majors.push(major);
  for (const nested of reg.nested_ellipses ?? []) {
    const m = Number(nested.ellipse?.semi_major_deg ?? 0);
    if (Number.isFinite(m) && m > 0) majors.push(m);
  }
  let outer = majors.length ? Math.max(...majors) : 0;
  if (outer < PEAK_RING_MAJOR_THRESHOLD_DEG) {
    outer = Math.max(outer, PEAK_RING_AOI_RADIUS_DEG);
  }
  return outer;
}

type SkyBase = {
  field_stars: FieldStar[];
  galactic_plane: number[][];
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
  distance_kpc?: number | null;
  rank_confidence?: number | null;
  composition?: string | null;
  life_window?: string | null;
  life_note?: string | null;
  rank_reasoning?: string | null;
};

type ViewMode = "full" | "zooming" | "zoomed";

/** SVG user-space camera (= viewBox). */
type Cam = { x: number; y: number; w: number; h: number };

const MIN_ZOOM = 1;
const MAX_ZOOM = 36;
const WHEEL_IN = 0.82;
const WHEEL_OUT = 1.22;
/**
 * Extra camera padding so the outer AOI spans ~80% of the viewport
 * (content / padded = 1 / (1 + pad) ≈ 0.80).
 */
const AOI_PAD = 0.25;
/** Target fraction of the viewport occupied by the outer AOI extent. */
export const AOI_VIEWPORT_FRACTION = 1 / (1 + AOI_PAD);
const DRAG_THRESH_PX = 4;

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

async function fetchSkyBase(): Promise<SkyBase> {
  try {
    const res = await fetch("/api/sky/base", { cache: "no-store" });
    if (!res.ok) return { field_stars: [], galactic_plane: [] };
    const body = (await res.json()) as SkyBase;
    return {
      field_stars: body.field_stars ?? [],
      // Intentionally unused — galactic plane guide removed from the skymap.
      galactic_plane: [],
    };
  } catch {
    return { field_stars: [], galactic_plane: [] };
  }
}

function formatHover(info: HoverInfo): string {
  const post = (info.posterior * 100).toFixed(1);
  const psky = (info.p_sky * 100).toFixed(2);
  const sim = info.simulated ? ` · ${strings.simulatedBadge}` : "";
  const conf =
    info.rank_confidence != null && !Number.isNaN(Number(info.rank_confidence))
      ? `${(Number(info.rank_confidence) * 100).toFixed(0)}%`
      : "—";
  const dist =
    info.distance_kpc != null && !Number.isNaN(Number(info.distance_kpc))
      ? `${Number(info.distance_kpc).toFixed(3)} kpc`
      : "—";
  const life = info.life_window || "—";
  const lines = [
    `#${info.rank} ${info.star_id} · ${info.class}${sim}`,
    `${strings.skyHoverPosterior}: ${post}% · ${strings.skyHoverPSky}: ${psky}% · ${strings.skyHoverConfidence}: ${conf}`,
    `RA ${info.ra_deg.toFixed(3)}° · Dec ${info.dec_deg.toFixed(3)}° · ${dist}`,
    `${strings.skyHoverLife}: ${life}`,
  ];
  if (info.composition) {
    lines.push(`${strings.skyHoverComposition}: ${info.composition}`);
  }
  if (info.life_note) {
    lines.push(info.life_note);
  } else if (info.rank_reasoning) {
    const short =
      info.rank_reasoning.length > 160
        ? `${info.rank_reasoning.slice(0, 157)}…`
        : info.rank_reasoning;
    lines.push(short);
  }
  return lines.join("\n");
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
    distance_kpc: row.distance_kpc,
    rank_confidence: row.rank_confidence ?? row.lit?.confidence ?? null,
    composition: row.composition ?? row.spectral_type ?? null,
    life_window: (() => {
      const life = row.life_expectancy?.optical_breakout_window;
      if (life && life !== "n/a" && life !== "") return life;
      const bw = row.breakout?.class_window;
      if (bw && bw !== "n/a" && bw !== "") return bw;
      return null;
    })(),
    life_note: row.life_expectancy?.stellar_stage_note ?? null,
    rank_reasoning: row.rank_reasoning ?? null,
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

function easeOutCubic(t: number): number {
  return 1 - (1 - t) ** 3;
}

function camZoom(c: Cam, contentW: number): number {
  return contentW > 0 ? contentW / Math.max(c.w, 1e-6) : 1;
}

function isNearFull(c: Cam, contentW: number, contentH: number): boolean {
  return (
    camZoom(c, contentW) <= 1.04 &&
    c.x <= contentW * 0.02 &&
    c.y <= contentH * 0.02
  );
}

/** Aspect-preserving camera covering `bounds` with padding, clamped to content. */
function camForBounds(
  bounds: { minX: number; minY: number; maxX: number; maxY: number },
  contentW: number,
  contentH: number,
  pad = AOI_PAD,
): Cam {
  let bw = Math.max(bounds.maxX - bounds.minX, 8);
  let bh = Math.max(bounds.maxY - bounds.minY, 8);
  const cx = (bounds.minX + bounds.maxX) / 2;
  const cy = (bounds.minY + bounds.maxY) / 2;
  bw *= 1 + pad;
  bh *= 1 + pad;
  const aspect = contentW / Math.max(contentH, 1);
  if (bw / bh > aspect) bh = bw / aspect;
  else bw = bh * aspect;

  const maxW = contentW / MIN_ZOOM;
  const minW = contentW / MAX_ZOOM;
  bw = Math.min(Math.max(bw, minW), maxW);
  bh = bw / aspect;

  let x = cx - bw / 2;
  let y = cy - bh / 2;
  x = Math.min(Math.max(x, 0), Math.max(0, contentW - bw));
  y = Math.min(Math.max(y, 0), Math.max(0, contentH - bh));
  return { x, y, w: bw, h: bh };
}

/**
 * Camera covering the **outer AOI** extent (ellipse outline ∪ peak-ring /
 * ranking aperture), padded so the AOI fills ~80% of the viewport.
 */
function outlineCam(
  reg: RegionPayload,
  contentW: number,
  contentH: number,
): Cam | null {
  const ring = outlineRing(reg);
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let n = 0;
  for (const pair of ring) {
    const p = raDecToMollweide(
      Number(pair[0]),
      Number(pair[1]),
      contentW,
      contentH,
    );
    if (!p) continue;
    minX = Math.min(minX, p.x);
    minY = Math.min(minY, p.y);
    maxX = Math.max(maxX, p.x);
    maxY = Math.max(maxY, p.y);
    n += 1;
  }
  const peak = raDecToMollweide(
    reg.peak.ra_deg,
    reg.peak.dec_deg,
    contentW,
    contentH,
  );
  if (peak) {
    minX = Math.min(minX, peak.x);
    minY = Math.min(minY, peak.y);
    maxX = Math.max(maxX, peak.x);
    maxY = Math.max(maxY, peak.y);
    n += 1;
  }

  // Expand to the outer ranking aperture (peak-ring floor for IceCube-scale).
  // Zoom must use this larger extent — not the tiny credible ellipse alone.
  const outerR = outerAoiRadiusDeg(reg);
  if (peak && outerR > 0) {
    const rPx = peakRingRadiusPx(
      reg.peak.ra_deg,
      reg.peak.dec_deg,
      contentW,
      contentH,
      outerR,
    );
    if (rPx != null) {
      minX = Math.min(minX, peak.x - rPx);
      minY = Math.min(minY, peak.y - rPx);
      maxX = Math.max(maxX, peak.x + rPx);
      maxY = Math.max(maxY, peak.y + rPx);
      n += 1;
    }
  }

  if (n < 2 || !Number.isFinite(minX)) {
    if (!peak) return null;
    const fov = Math.max(reg.fov_deg || 20, outerR * 2 || 10);
    const half = (fov / 360) * contentW * 0.55;
    return camForBounds(
      {
        minX: peak.x - half,
        minY: peak.y - half * (contentH / contentW),
        maxX: peak.x + half,
        maxY: peak.y + half * (contentH / contentW),
      },
      contentW,
      contentH,
    );
  }
  return camForBounds({ minX, minY, maxX, maxY }, contentW, contentH);
}

function clampCam(c: Cam, contentW: number, contentH: number): Cam {
  const aspect = contentW / Math.max(contentH, 1);
  let w = c.w;
  const maxW = contentW / MIN_ZOOM;
  const minW = contentW / MAX_ZOOM;
  w = Math.min(Math.max(w, minW), maxW);
  const h = w / aspect;
  let x = c.x;
  let y = c.y;
  if (w >= contentW - 0.5) {
    return { x: 0, y: 0, w: contentW, h: contentH };
  }
  x = Math.min(Math.max(x, 0), contentW - w);
  y = Math.min(Math.max(y, 0), contentH - h);
  return { x, y, w, h };
}

export function mountSky(
  host: HTMLElement,
  resetBtn: HTMLButtonElement,
): () => void {
  host.innerHTML = `
    <div class="sky-stage" data-role="stage">
      <div class="sky-world" data-role="world">
        <div class="sky-zoomable" data-role="zoomable">
          <div class="sky-frame" data-role="frame">
            <svg class="sky-svg" id="sky-map-view" data-role="svg" role="img" aria-label="${strings.skyTitle}"></svg>
          </div>
        </div>
      </div>
      <div class="sky-hover" data-role="hover" hidden></div>
      <div class="sky-meta" data-role="meta" hidden></div>
    </div>
  `;

  const world = host.querySelector<HTMLElement>("[data-role=world]")!;
  const frame = host.querySelector<HTMLElement>("[data-role=frame]")!;
  const svg = host.querySelector<SVGSVGElement>("[data-role=svg]")!;
  const hoverEl = host.querySelector<HTMLElement>("[data-role=hover]")!;
  const meta = host.querySelector<HTMLElement>("[data-role=meta]")!;

  let region: RegionPayload | null = null;
  let skyBase: SkyBase = { field_stars: [], galactic_plane: [] };
  let animatedAlertId: string | null = null;
  let fullSkyChoice: { alertId: string; missionEpoch: number } | null = null;
  let seenZoomNonce = 0;
  let renderSeq = 0;
  /**
   * Zoom generation — bumps only when the mission target changes (alert / nonce),
   * not when candidates/selection refresh. Candidate emits used to bump renderSeq
   * and abort the 550ms zoom delay (map stuck at full sky).
   */
  let zoomGen = 0;
  /** Alert id the in-flight zoom animation was started for (stale if mismatched). */
  let zoomAlertId: string | null = null;
  let viewMode: ViewMode = "full";
  /** Mollweide content aspect — projection is 2:1 (width:height). */
  const MOLLWEIDE_AR = 2;
  let contentW = 640;
  let contentH = 320;
  let cam: Cam = { x: 0, y: 0, w: contentW, h: contentH };
  let camRaf = 0;
  let zoomDelayTimer = 0;
  let pointerDragging = false;
  let pointerMoved = false;
  let pointerId: number | null = null;
  let lastPtrX = 0;
  let lastPtrY = 0;
  let skipStarClick = false;
  /** Skip re-paints when only selection/voice chrome changed (hover must not tear down SVG). */
  let lastSkyKey = "";

  /**
   * Size the SVG frame to the Mollweide aspect inside the stage.
   * The stage itself is CSS-sized to 2:1; this fills it exactly when layout
   * has settled, and letterboxes if the host briefly differs.
   */
  const fitFrame = () => {
    const ar = MOLLWEIDE_AR;
    const pw = world.clientWidth || host.clientWidth || 640;
    const ph = world.clientHeight || host.clientHeight || 360;
    let w = pw;
    let h = w / ar;
    if (h > ph + 0.5) {
      h = ph;
      w = h * ar;
    }
    // Prefer integer CSS px so SVG width/height match the visible viewport.
    w = Math.max(1, Math.floor(w));
    h = Math.max(1, Math.round(w / ar));
    if (h > ph) {
      h = Math.max(1, Math.floor(ph));
      w = Math.max(1, Math.round(h * ar));
    }
    frame.style.width = `${w}px`;
    frame.style.height = `${h}px`;
    return { w: frame.clientWidth || w, h: frame.clientHeight || h };
  };

  const showHover = (
    info: HoverInfo | null,
    clientX?: number,
    clientY?: number,
  ) => {
    if (!info) {
      hoverEl.hidden = true;
      hoverEl.textContent = "";
      return;
    }
    hoverEl.hidden = false;
    hoverEl.textContent = formatHover(info);
    if (clientX != null && clientY != null) {
      const rect = host.getBoundingClientRect();
      const x = Math.min(clientX - rect.left + 12, rect.width - 280);
      const y = Math.min(clientY - rect.top + 12, rect.height - 160);
      hoverEl.style.left = `${Math.max(8, x)}px`;
      hoverEl.style.top = `${Math.max(8, y)}px`;
    }
  };

  const phaseLabel = () => {
    if (viewMode === "full") return strings.skyModeFull;
    if (viewMode === "zooming") return strings.skyModeZoom;
    return strings.skyModeFocus;
  };

  const setMeta = (skymap: SkymapPayload | null, reg: RegionPayload | null) => {
    meta.hidden = false;
    if (!skymap) {
      meta.innerHTML = `
        <span>${strings.skyModeFull}</span>
        <span>${skyBase.field_stars.length.toLocaleString()} BSC5 field stars</span>
      `;
      return;
    }
    const peak = reg?.peak ?? skymap.peak;
    const area = reg?.credible_deg2 ?? skymap.credible_90_deg2;
    const ell = reg?.ellipse;
    const axes = ell
      ? ` · oval ${ell.semi_major_deg.toFixed(1)}°×${ell.semi_minor_deg.toFixed(1)}°`
      : "";
    const z = camZoom(cam, contentW);
    const zoomHint = z > 1.05 ? ` · ${z.toFixed(1)}×` : "";
    meta.innerHTML = `
      <span>${strings.skyPeak} RA ${peak.ra_deg.toFixed(2)}° · Dec ${peak.dec_deg.toFixed(2)}°</span>
      <span>90% · ${area.toFixed(1)} deg²${axes}</span>
      <span class="sky-mode">${phaseLabel()}${zoomHint}</span>
      ${(reg?.simulated ?? skymap.simulated)
        ? `<span class="badge sim">${strings.simulatedBadge}</span>`
        : `<span class="badge real">${strings.realBadge}</span>`}
    `;
  };

  const applyCam = (next: Cam, opts?: { meta?: boolean }) => {
    cam = clampCam(next, contentW, contentH);
    svg.setAttribute("viewBox", `${cam.x} ${cam.y} ${cam.w} ${cam.h}`);
    if (isNearFull(cam, contentW, contentH) && viewMode !== "zooming") {
      viewMode = "full";
    } else if (viewMode !== "zooming") {
      viewMode = "zoomed";
    }
    if (opts?.meta !== false) {
      const { skymap } = getState();
      setMeta(skymap, region);
    }
  };

  const cancelCamAnim = () => {
    if (camRaf) {
      cancelAnimationFrame(camRaf);
      camRaf = 0;
    }
    window.clearTimeout(zoomDelayTimer);
    zoomDelayTimer = 0;
    zoomAlertId = null;
    if (viewMode === "zooming") {
      viewMode = isNearFull(cam, contentW, contentH) ? "full" : "zoomed";
    }
  };

  const animateCamTo = (
    target: Cam,
    skymap: SkymapPayload,
    reg: RegionPayload,
    durationMs = 1550,
    genAtStart = zoomGen,
  ) => {
    cancelCamAnim();
    zoomAlertId = skymap.alert_id;
    const from = { ...cam };
    const to = clampCam(target, contentW, contentH);
    viewMode = "zooming";
    setMeta(skymap, reg);
    const t0 = performance.now();
    const tick = (now: number) => {
      // Ignore frames after a newer scenario took over (not candidate refreshes).
      if (genAtStart !== zoomGen || zoomAlertId !== skymap.alert_id) {
        camRaf = 0;
        return;
      }
      const { skymap: live } = getState();
      if (!live || live.alert_id !== skymap.alert_id) {
        camRaf = 0;
        return;
      }
      const t = Math.min(1, (now - t0) / durationMs);
      const e = easeOutCubic(t);
      applyCam(
        {
          x: from.x + (to.x - from.x) * e,
          y: from.y + (to.y - from.y) * e,
          w: from.w + (to.w - from.w) * e,
          h: from.h + (to.h - from.h) * e,
        },
        { meta: false },
      );
      if (t < 1) {
        camRaf = requestAnimationFrame(tick);
        return;
      }
      camRaf = 0;
      zoomAlertId = null;
      viewMode = "zoomed";
      applyCam(to);
      setMeta(skymap, reg);
    };
    camRaf = requestAnimationFrame(tick);
  };

  const showFieldTip = (
    tip: string | null,
    clientX?: number,
    clientY?: number,
  ) => {
    if (!tip) {
      hoverEl.hidden = true;
      hoverEl.textContent = "";
      return;
    }
    hoverEl.hidden = false;
    hoverEl.textContent = tip;
    if (clientX != null && clientY != null) {
      const rect = host.getBoundingClientRect();
      const x = Math.min(clientX - rect.left + 12, rect.width - 280);
      const y = Math.min(clientY - rect.top + 12, rect.height - 120);
      hoverEl.style.left = `${Math.max(8, x)}px`;
      hoverEl.style.top = `${Math.max(8, y)}px`;
    }
  };

  const wireStar = (g: SVGGElement, row: CandidateRow, rank: number) => {
    const info = candidateHover(row, rank);
    g.style.cursor = "pointer";
    g.addEventListener("pointerenter", (ev) => {
      if (pointerDragging) return;
      showHover(info, ev.clientX, ev.clientY);
      selectStar(row.star_id);
    });
    g.addEventListener("pointermove", (ev) => {
      if (pointerDragging) return;
      showHover(info, ev.clientX, ev.clientY);
    });
    g.addEventListener("pointerleave", () => {
      if (!pointerDragging) showHover(null);
    });
    g.addEventListener("click", (ev) => {
      if (skipStarClick || pointerMoved) {
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
      selectStar(row.star_id);
    });
  };

  const paintSvg = (
    reg: RegionPayload | null,
    candidates: CandidateRow[],
  ): { w: number; h: number } => {
    const { w, h } = fitFrame();
    const sx = contentW > 0 ? w / contentW : 1;
    const sy = contentH > 0 ? h / contentH : 1;
    const prevCam = cam;
    contentW = w;
    contentH = h;

    svg.setAttribute("width", String(w));
    svg.setAttribute("height", String(h));
    svg.innerHTML = "";

    const root = createSvgEl("g");
    root.setAttribute("data-role", "scene");

    const limb = createSvgEl("path");
    limb.setAttribute("d", mollweideLimbPath(w, h));
    limb.setAttribute("class", "sky-limb");
    root.appendChild(limb);

    drawEquatorialGrid(root, w, h);

    // Always prefer the dense /api/sky/base catalog. Region payloads omit the
    // full ~8k-star list so region.json stays small; ranked progenitors are
    // drawn separately below as .sky-star overlays.
    const field = skyBase.field_stars.length
      ? skyBase.field_stars
      : (reg?.field_stars ?? []);
    const fieldG = createSvgEl("g");
    fieldG.setAttribute("class", "sky-field");
    for (const star of field) {
      const p = raDecToMollweide(star.ra_deg, star.dec_deg, w, h);
      if (!p) continue;
      const c = createSvgEl("circle");
      c.setAttribute("cx", String(p.x));
      c.setAttribute("cy", String(p.y));
      const v =
        star.vmag != null && !Number.isNaN(Number(star.vmag))
          ? Number(star.vmag)
          : 5.5;
      const { r, opacity } = starStyleFromVmag(v);
      c.setAttribute("r", String(r));
      c.setAttribute("fill-opacity", String(opacity));
      c.setAttribute("class", "sky-field-star");
      c.setAttribute("data-id", star.star_id);
      const label = star.common_name || star.star_id;
      c.setAttribute(
        "data-tip",
        `${label} · V ${v.toFixed(2)} · RA ${star.ra_deg.toFixed(3)}° · Dec ${star.dec_deg.toFixed(3)}°`,
      );
      fieldG.appendChild(c);
    }
    fieldG.addEventListener("pointerover", (ev) => {
      if (pointerDragging) return;
      const t = ev.target as Element | null;
      if (!t || t.tagName.toLowerCase() !== "circle") return;
      const tip = t.getAttribute("data-tip");
      if (tip) showFieldTip(tip, ev.clientX, ev.clientY);
    });
    fieldG.addEventListener("pointermove", (ev) => {
      if (pointerDragging) return;
      const t = ev.target as Element | null;
      if (!t || t.tagName.toLowerCase() !== "circle") return;
      const tip = t.getAttribute("data-tip");
      if (tip) showFieldTip(tip, ev.clientX, ev.clientY);
    });
    fieldG.addEventListener("pointerout", (ev) => {
      const related = ev.relatedTarget as Node | null;
      if (related && fieldG.contains(related)) return;
      if (!pointerDragging) showFieldTip(null);
    });
    root.appendChild(fieldG);

    if (reg) {
      // Two intentional mint AOI marks only — no HEALPix fills or nested light
      // ellipses. Opacity is assigned by projected size (larger/outer = more
      // transparent; smaller/inner = less), never by CSS class name —
      // IceCube's peak ring is visually outer.
      const ring = outlineRing(reg);
      const ovalPts = projectRing(ring, w, h);
      const aoiMarks: Array<{ el: Element; sizePx: number }> = [];
      const peakPt = reg.peak
        ? raDecToMollweide(reg.peak.ra_deg, reg.peak.dec_deg, w, h)
        : null;
      const ovalCenter = peakPt
        ? peakPt
        : reg.ellipse
          ? raDecToMollweide(reg.ellipse.ra_deg, reg.ellipse.dec_deg, w, h)
          : null;

      if (ovalPts) {
        const oval = createSvgEl("polygon");
        oval.setAttribute("points", ovalPts);
        oval.setAttribute("class", "sky-outline");
        oval.setAttribute("vector-effect", "non-scaling-stroke");
        oval.setAttribute("fill", "none");
        root.appendChild(oval);
        const cx = ovalCenter?.x ?? w / 2;
        const cy = ovalCenter?.y ?? h / 2;
        aoiMarks.push({
          el: oval,
          sizePx: projectedOutlineRadiusPx(ovalPts, cx, cy),
        });
      }
      // Tiny IceCube-scale ellipses get a readable peak ring sized to the
      // shared outer-AOI angular radius (ranking aperture).
      const major = Number(reg.ellipse?.semi_major_deg ?? 0);
      const needsPeakRing =
        !ovalPts || !(major > 0) || major < PEAK_RING_MAJOR_THRESHOLD_DEG;
      if (reg.peak && needsPeakRing) {
        const peak = peakPt;
        const rPx = peakRingRadiusPx(
          reg.peak.ra_deg,
          reg.peak.dec_deg,
          w,
          h,
        );
        if (peak && rPx != null) {
          const ringEl = createSvgEl("circle");
          ringEl.setAttribute("cx", String(peak.x));
          ringEl.setAttribute("cy", String(peak.y));
          ringEl.setAttribute("r", String(rPx));
          ringEl.setAttribute("class", "sky-outline-peak");
          ringEl.setAttribute("vector-effect", "non-scaling-stroke");
          ringEl.setAttribute("fill", "none");
          root.appendChild(ringEl);
          aoiMarks.push({ el: ringEl, sizePx: rPx });
        }
      }
      assignAoiStrokeBySize(aoiMarks);
    }

    const fieldById = new Map(
      field.map((s) => [s.star_id, s] as const),
    );
    const fieldElById = new Map<string, Element>();
    for (const el of Array.from(fieldG.querySelectorAll("[data-id]"))) {
      const id = el.getAttribute("data-id");
      if (id) fieldElById.set(id, el);
    }
    const nRanked = Math.max(candidates.length, 1);
    candidates.forEach((row, idx) => {
      const p = raDecToMollweide(row.ra_deg, row.dec_deg, w, h);
      if (!p) return;
      // Hide the matching field-star underlay so size does not visually double.
      const under = fieldById.get(row.star_id);
      const underEl = fieldElById.get(row.star_id);
      if (underEl) underEl.setAttribute("visibility", "hidden");
      const g = createSvgEl("g");
      g.setAttribute("class", "sky-star");
      const c = createSvgEl("circle");
      c.setAttribute("cx", String(p.x));
      c.setAttribute("cy", String(p.y));
      let vmag =
        (row as CandidateRow & { vmag?: number | null }).vmag ??
        under?.vmag ??
        null;
      if (vmag == null) {
        let best: { d: number; v: number } | null = null;
        for (const s of field) {
          if (s.vmag == null) continue;
          const dra =
            (s.ra_deg - row.ra_deg) *
            Math.cos(((s.dec_deg + row.dec_deg) * Math.PI) / 360);
          const ddec = s.dec_deg - row.dec_deg;
          const d = Math.hypot(dra, ddec);
          if (d < 0.05 && (!best || d < best.d)) {
            best = { d, v: Number(s.vmag) };
          }
        }
        vmag = best?.v ?? null;
      }
      // Same magnitude radius as field stars — do not enlarge after replay.
      const { r } = starStyleFromVmag(vmag);
      // Pure red; opacity by rank (1st most opaque → lower ranks more transparent).
      const opacity = Math.max(0.22, 1 - (idx / nRanked) * 0.78);
      c.setAttribute("r", String(r));
      c.setAttribute("fill", "#ff0000");
      c.setAttribute("fill-opacity", String(opacity));
      c.setAttribute("stroke", "none");
      g.appendChild(c);
      wireStar(g, row, idx + 1);
      root.appendChild(g);
    });

    svg.appendChild(root);

    applyCam(
      {
        x: prevCam.x * sx,
        y: prevCam.y * sy,
        w: prevCam.w * sx,
        h: prevCam.h * sy,
      },
      { meta: false },
    );
    return { w, h };
  };

  const resetToFull = () => {
    // Invalidate queued replay frames as well as the active camera animation.
    // Candidate refreshes keep this all-sky view until a new replay starts.
    zoomGen += 1;
    cancelCamAnim();
    const { skymap, skyZoomNonce, missionEpoch } = getState();
    animatedAlertId = skymap?.alert_id ?? null;
    fullSkyChoice = skymap ? { alertId: skymap.alert_id, missionEpoch } : null;
    seenZoomNonce = skyZoomNonce;
    showHover(null);
    const full = { x: 0, y: 0, w: contentW, h: contentH };
    viewMode = "full";
    applyCam(full);
    setMeta(skymap, region);
  };

  const runZoomSequence = (
    skymap: SkymapPayload,
    reg: RegionPayload,
    candidates: CandidateRow[],
    genAtStart: number,
  ) => {
    if (genAtStart !== zoomGen) return;
    if (reg.alert_id !== skymap.alert_id) return;
    const live = getState().skymap;
    if (!live || live.alert_id !== skymap.alert_id) return;

    cancelCamAnim();
    paintSvg(reg, candidates);
    const target = outlineCam(reg, contentW, contentH);
    applyCam({ x: 0, y: 0, w: contentW, h: contentH });
    viewMode = "full";
    setMeta(skymap, reg);

    if (!target) {
      viewMode = "full";
      setMeta(skymap, reg);
      return;
    }

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      viewMode = "zoomed";
      applyCam(target);
      setMeta(skymap, reg);
      return;
    }

    zoomAlertId = skymap.alert_id;
    zoomDelayTimer = window.setTimeout(() => {
      if (genAtStart !== zoomGen) return;
      const still = getState().skymap;
      if (!still || still.alert_id !== skymap.alert_id) return;
      if (!region || region.alert_id !== skymap.alert_id) return;
      animateCamTo(target, skymap, reg, 1600, genAtStart);
    }, 550);
  };

  const showBaseSky = () => {
    cancelCamAnim();
    viewMode = "full";
    paintSvg(null, []);
    applyCam({ x: 0, y: 0, w: contentW, h: contentH });
    setMeta(null, null);
  };

  const showEvent = (
    skymap: SkymapPayload,
    reg: RegionPayload,
    candidates: CandidateRow[],
    animate: boolean,
    genAtStart: number,
  ) => {
    if (animate) {
      // Capture zoomGen so a later scenario switch cancels this rAF work.
      requestAnimationFrame(() => {
        if (genAtStart !== zoomGen) return;
        runZoomSequence(skymap, reg, candidates, genAtStart);
      });
      return;
    }
    // Candidate/selection refresh during zoom: keep the camera animation.
    // (Re-painting would rebuild the SVG and fight the viewBox tween.)
    if (viewMode === "zooming" && zoomAlertId === skymap.alert_id) return;
    if (viewMode === "zooming") cancelCamAnim();
    paintSvg(reg, candidates);
    setMeta(skymap, reg);
  };

  const onWheel = (ev: WheelEvent) => {
    ev.preventDefault();
    if (viewMode === "zooming") cancelCamAnim();
    const rect = svg.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) return;
    const fracX = (ev.clientX - rect.left) / rect.width;
    const fracY = (ev.clientY - rect.top) / rect.height;
    const mx = cam.x + fracX * cam.w;
    const my = cam.y + fracY * cam.h;
    const factor = ev.deltaY < 0 ? WHEEL_IN : WHEEL_OUT;
    const newW = cam.w * factor;
    const newH = cam.h * factor;
    applyCam({
      x: mx - fracX * newW,
      y: my - fracY * newH,
      w: newW,
      h: newH,
    });
    showHover(null);
  };

  const onPointerMove = (ev: PointerEvent) => {
    if (!pointerDragging || pointerId !== ev.pointerId) return;
    // Ignore coalesced companion events with no movement.
    const rect = svg.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) return;
    const dxScreen = ev.clientX - lastPtrX;
    const dyScreen = ev.clientY - lastPtrY;
    if (dxScreen === 0 && dyScreen === 0) return;
    if (!pointerMoved && Math.hypot(dxScreen, dyScreen) >= DRAG_THRESH_PX) {
      pointerMoved = true;
      skipStarClick = true;
      showHover(null);
      if (viewMode === "zooming") cancelCamAnim();
    }
    if (!pointerMoved) return;
    const dx = (dxScreen / rect.width) * cam.w;
    const dy = (dyScreen / rect.height) * cam.h;
    lastPtrX = ev.clientX;
    lastPtrY = ev.clientY;
    applyCam({ x: cam.x - dx, y: cam.y - dy, w: cam.w, h: cam.h });
  };

  const onPointerUp = (ev: PointerEvent) => {
    if (pointerId !== null && pointerId !== ev.pointerId) return;
    pointerDragging = false;
    pointerId = null;
    svg.classList.remove("is-panning");
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerUp);
    if (skipStarClick) {
      window.setTimeout(() => {
        skipStarClick = false;
        pointerMoved = false;
      }, 0);
    }
  };

  const onPointerDown = (ev: PointerEvent) => {
    // Accept primary mouse / touch / pen. Some CDP mouse streams omit button=0
    // on pointerdown; `buttons` bitmask is more reliable mid-gesture.
    if (ev.pointerType === "mouse" && ev.button !== 0 && ev.buttons === 0) {
      return;
    }
    pointerDragging = true;
    pointerMoved = false;
    skipStarClick = false;
    pointerId = ev.pointerId;
    lastPtrX = ev.clientX;
    lastPtrY = ev.clientY;
    svg.classList.add("is-panning");
    // Window-level move/up so pan keeps working if the cursor leaves the SVG.
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerUp);
  };

  const onDblClick = (ev: MouseEvent) => {
    ev.preventDefault();
    resetToFull();
  };

  svg.addEventListener("wheel", onWheel, { passive: false });
  svg.addEventListener("pointerdown", onPointerDown);
  svg.addEventListener("dblclick", onDblClick);
  resetBtn.addEventListener("click", resetToFull);

  const render = async () => {
    // Avoid tearing down SVG nodes mid-pan (loses the gesture).
    if (pointerDragging) return;
    const seq = ++renderSeq;
    const { skymap, candidates, suppressSkyZoomOnce, skyZoomNonce, missionEpoch } =
      getState();

    // Hover calls selectStar → store emit; ignore paints that only change selection.
    const skyKey = [
      skymap?.alert_id ?? "",
      skyZoomNonce,
      missionEpoch,
      suppressSkyZoomOnce ? 1 : 0,
      candidates.map((c) => c.star_id).join(","),
      candidates.map((c) => c.posterior.toFixed(5)).join(","),
    ].join("|");
    if (skyKey === lastSkyKey && viewMode !== "zooming") {
      return;
    }

    if (!skyBase.field_stars.length) {
      skyBase = await fetchSkyBase();
      if (seq !== renderSeq) return;
    }

    if (!skymap) {
      showHover(null);
      cancelCamAnim();
      animatedAlertId = null;
      region = null;
      zoomGen += 1;
      showBaseSky();
      lastSkyKey = skyKey;
      return;
    }

    // Drop the previous scenario's region immediately so we never paint or
    // zoom against stale AOI geometry while the new region.json is fetching.
    if (region && region.alert_id !== skymap.alert_id) {
      cancelCamAnim();
      region = null;
      animatedAlertId = null;
      zoomGen += 1;
      viewMode = "full";
      paintSvg(null, candidates);
      applyCam({ x: 0, y: 0, w: contentW, h: contentH });
      setMeta(skymap, null);
    }

    if (!region || region.alert_id !== skymap.alert_id) {
      const wantId = skymap.alert_id;
      const next = await fetchRegion(wantId);
      if (seq !== renderSeq) return;
      const live = getState().skymap;
      if (!live || live.alert_id !== wantId) return;
      region = next;
    }

    if (!region) {
      paintSvg(null, candidates);
      applyCam({ x: 0, y: 0, w: contentW, h: contentH });
      setMeta(skymap, null);
      lastSkyKey = skyKey;
      return;
    }

    if (skyZoomNonce !== seenZoomNonce) {
      seenZoomNonce = skyZoomNonce;
      // Nonce bump from beginScenarioSwitch clears skymap first; only reset
      // animatedAlertId when we actually have a map to (re)play against.
      if (skymap) {
        animatedAlertId = null;
        zoomGen += 1;
      }
    }

    const keepFullSky =
      fullSkyChoice?.alertId === skymap.alert_id &&
      fullSkyChoice.missionEpoch === missionEpoch;
    let shouldAnimate = !keepFullSky && skymap.alert_id !== animatedAlertId;
    if (suppressSkyZoomOnce) {
      shouldAnimate = false;
      animatedAlertId = skymap.alert_id;
      clearSkyZoomSuppress();
      cancelCamAnim();
      zoomGen += 1;
      viewMode = "full";
      paintSvg(region, candidates);
      applyCam({ x: 0, y: 0, w: contentW, h: contentH });
      setMeta(skymap, region);
      lastSkyKey = skyKey;
      return;
    }
    const genAtStart = zoomGen;
    if (shouldAnimate) {
      animatedAlertId = skymap.alert_id;
      zoomGen += 1;
    }
    showEvent(
      skymap,
      region,
      candidates,
      shouldAnimate,
      shouldAnimate ? zoomGen : genAtStart,
    );
    lastSkyKey = skyKey;
  };

  const unsub = subscribe(() => {
    void render();
  });
  const onResize = () => {
    const { skymap, candidates } = getState();
    if (viewMode === "zooming") return;
    if (skymap && region) {
      paintSvg(region, candidates);
      setMeta(skymap, region);
    } else {
      showBaseSky();
    }
  };
  window.addEventListener("resize", onResize);

  return () => {
    unsub();
    window.removeEventListener("resize", onResize);
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerUp);
    svg.removeEventListener("wheel", onWheel);
    svg.removeEventListener("pointerdown", onPointerDown);
    svg.removeEventListener("dblclick", onDblClick);
    resetBtn.removeEventListener("click", resetToFull);
    cancelCamAnim();
  };
}
