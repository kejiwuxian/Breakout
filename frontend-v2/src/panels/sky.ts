/**
 * Pure-SVG Mollweide skymap. Public catalog stars + galactic plane + HEALPix
 * localization cells + smooth 90% oval. Zoom is a CSS transform on one SVG —
 * no raster PNG swap.
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
  projectPolyline,
  projectRing,
} from "../sky/svgMap";

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
  prob_cells?: ProbCell[];
  field_stars?: FieldStar[];
  galactic_plane?: number[][];
  shape?: string;
  render?: string;
  simulated: boolean;
};

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
      galactic_plane: body.galactic_plane ?? [],
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
    life_window:
      row.life_expectancy?.optical_breakout_window ??
      row.breakout?.class_window ??
      null,
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

export function mountSky(host: HTMLElement): () => void {
  host.innerHTML = `
    <div class="sky-stage" data-role="stage">
      <div class="sky-world" data-role="world">
        <div class="sky-zoomable" data-role="zoomable">
          <div class="sky-frame" data-role="frame">
            <svg class="sky-svg" data-role="svg" role="img" aria-label="${strings.skyTitle}"></svg>
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
  let seenZoomNonce = 0;
  let renderSeq = 0;
  let viewMode: ViewMode = "full";
  let zoomTimer = 0;
  let settleTimer = 0;

  const fitFrame = () => {
    const ar = 2;
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
    return { w: frame.clientWidth || w, h: frame.clientHeight || h };
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
        <span>${skyBase.field_stars.length} public catalog stars</span>
      `;
      return;
    }
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

  const clearFrameZoom = () => {
    frame.style.transition = "none";
    frame.classList.remove("is-zoomed");
    frame.style.transform = "none";
    frame.style.transformOrigin = "50% 50%";
    void frame.offsetWidth;
    frame.style.transition = "";
  };

  const paintSvg = (
    reg: RegionPayload | null,
    candidates: CandidateRow[],
  ): { w: number; h: number } => {
    const { w, h } = fitFrame();
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.setAttribute("width", String(w));
    svg.setAttribute("height", String(h));
    svg.innerHTML = "";

    const root = createSvgEl("g");
    root.setAttribute("data-role", "scene");

    // Limb + night fill
    const limb = createSvgEl("path");
    limb.setAttribute("d", mollweideLimbPath(w, h));
    limb.setAttribute("class", "sky-limb");
    root.appendChild(limb);

    drawEquatorialGrid(root, w, h);

    const plane = reg?.galactic_plane?.length
      ? reg.galactic_plane
      : skyBase.galactic_plane;
    if (plane.length >= 2) {
      const gp = createSvgEl("path");
      gp.setAttribute("d", projectPolyline(plane, w, h));
      gp.setAttribute("class", "sky-galactic");
      root.appendChild(gp);
    }

    const field = reg?.field_stars?.length
      ? reg.field_stars
      : skyBase.field_stars;
    const fieldG = createSvgEl("g");
    fieldG.setAttribute("class", "sky-field");
    for (const star of field) {
      const p = raDecToMollweide(star.ra_deg, star.dec_deg, w, h);
      if (!p) continue;
      const c = createSvgEl("circle");
      c.setAttribute("cx", String(p.x));
      c.setAttribute("cy", String(p.y));
      c.setAttribute("r", "1.6");
      c.setAttribute("class", "sky-field-star");
      c.setAttribute("data-id", star.star_id);
      fieldG.appendChild(c);
    }
    root.appendChild(fieldG);

    if (reg) {
      const cellsG = createSvgEl("g");
      cellsG.setAttribute("class", "sky-prob-cells");
      for (const cell of reg.prob_cells ?? []) {
        const pts = projectRing(cell.corners, w, h);
        if (!pts) continue;
        const poly = createSvgEl("polygon");
        poly.setAttribute("points", pts);
        poly.setAttribute("class", "sky-prob-cell");
        poly.setAttribute(
          "fill-opacity",
          String(Math.min(0.75, 0.12 + 0.65 * (cell.weight || 0))),
        );
        cellsG.appendChild(poly);
      }
      root.appendChild(cellsG);

      for (const nest of reg.nested_ellipses ?? []) {
        const pts = projectRing(nest.outline, w, h);
        if (!pts) continue;
        const poly = createSvgEl("polygon");
        poly.setAttribute("points", pts);
        poly.setAttribute(
          "class",
          nest.level >= 0.85 ? "sky-nest-outer" : "sky-nest-inner",
        );
        root.appendChild(poly);
      }

      const ovalPts = projectRing(outlineRing(reg), w, h);
      if (ovalPts) {
        const oval = createSvgEl("polygon");
        oval.setAttribute("points", ovalPts);
        oval.setAttribute("class", "sky-outline");
        root.appendChild(oval);
      }
    }

    const rankedIds = new Set(candidates.map((c) => c.star_id));
    candidates.forEach((row, idx) => {
      const p = raDecToMollweide(row.ra_deg, row.dec_deg, w, h);
      if (!p) return;
      const g = createSvgEl("g");
      g.setAttribute("class", "sky-star");
      const c = createSvgEl("circle");
      c.setAttribute("cx", String(p.x));
      c.setAttribute("cy", String(p.y));
      c.setAttribute("r", idx === 0 ? "6.5" : "5");
      g.appendChild(c);
      wireStar(g, row, idx + 1);
      root.appendChild(g);
      rankedIds.add(row.star_id);
    });

    svg.appendChild(root);
    return { w, h };
  };

  const settleZoomed = (
    skymap: SkymapPayload,
    reg: RegionPayload,
    _candidates: CandidateRow[],
  ) => {
    // Stay on the same SVG — only the mode label changes after the zoom eases.
    viewMode = "zoomed";
    setMeta(skymap, reg);
  };

  const runZoomSequence = (
    skymap: SkymapPayload,
    reg: RegionPayload,
    candidates: CandidateRow[],
  ) => {
    const { w, h } = paintSvg(reg, candidates);
    const pt = raDecToMollweide(reg.peak.ra_deg, reg.peak.dec_deg, w, h);
    const major = reg.ellipse?.semi_major_deg ?? Math.sqrt(reg.credible_deg2 / Math.PI);
    const ovalPx = Math.max(major * (w / 360) * 1.35, 10);
    const scale = Math.min(
      Math.max((Math.min(w, h) * 0.62) / ovalPx, 5),
      20,
    );

    viewMode = "full";
    clearFrameZoom();
    if (pt) frame.style.transformOrigin = `${pt.x.toFixed(1)}px ${pt.y.toFixed(1)}px`;
    setMeta(skymap, reg);

    window.clearTimeout(zoomTimer);
    window.clearTimeout(settleTimer);

    zoomTimer = window.setTimeout(() => {
      viewMode = "zooming";
      setMeta(skymap, reg);
      // Commit origin first, then scale on the next frame for a smooth CSS transition.
      requestAnimationFrame(() => {
        frame.classList.add("is-zoomed");
        frame.style.transform = `scale(${scale.toFixed(3)})`;
      });
      settleTimer = window.setTimeout(() => {
        settleZoomed(skymap, reg, candidates);
      }, 1700);
    }, 650);
  };

  const showBaseSky = () => {
    viewMode = "full";
    clearFrameZoom();
    paintSvg(null, []);
    setMeta(null, null);
  };

  const showEvent = (
    skymap: SkymapPayload,
    reg: RegionPayload,
    candidates: CandidateRow[],
    animate: boolean,
  ) => {
    if (animate) {
      requestAnimationFrame(() => runZoomSequence(skymap, reg, candidates));
      return;
    }
    if (viewMode === "zooming") return;
    if (viewMode === "zoomed") {
      settleZoomed(skymap, reg, candidates);
      return;
    }
    viewMode = "full";
    clearFrameZoom();
    paintSvg(reg, candidates);
    setMeta(skymap, reg);
  };

  const render = async () => {
    const seq = ++renderSeq;
    const { skymap, candidates, suppressSkyZoomOnce, skyZoomNonce } = getState();

    if (!skyBase.field_stars.length) {
      skyBase = await fetchSkyBase();
      if (seq !== renderSeq) return;
    }

    if (!skymap) {
      showHover(null);
      window.clearTimeout(zoomTimer);
      window.clearTimeout(settleTimer);
      animatedAlertId = null;
      region = null;
      showBaseSky();
      return;
    }

    if (!region || region.alert_id !== skymap.alert_id) {
      const next = await fetchRegion(skymap.alert_id);
      if (seq !== renderSeq) return;
      region = next;
    }

    if (!region) {
      paintSvg(null, candidates);
      setMeta(skymap, null);
      return;
    }

    if (skyZoomNonce !== seenZoomNonce) {
      seenZoomNonce = skyZoomNonce;
      animatedAlertId = null;
    }

    let shouldAnimate = skymap.alert_id !== animatedAlertId;
    if (suppressSkyZoomOnce) {
      shouldAnimate = false;
      animatedAlertId = skymap.alert_id;
      clearSkyZoomSuppress();
    } else if (shouldAnimate) {
      animatedAlertId = skymap.alert_id;
    }
    showEvent(skymap, region, candidates, shouldAnimate);
  };

  const unsub = subscribe(() => {
    void render();
  });
  const onResize = () => {
    const { skymap, candidates } = getState();
    if (viewMode === "zooming") return;
    if (skymap && region) {
      if (viewMode === "zoomed") settleZoomed(skymap, region, candidates);
      else {
        paintSvg(region, candidates);
        setMeta(skymap, region);
      }
    } else {
      showBaseSky();
    }
  };
  window.addEventListener("resize", onResize);

  return () => {
    unsub();
    window.removeEventListener("resize", onResize);
    window.clearTimeout(zoomTimer);
    window.clearTimeout(settleTimer);
  };
}
