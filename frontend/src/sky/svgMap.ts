/**
 * Pure-SVG Mollweide helpers. Projection math is public-domain spherical
 * astronomy; star positions come from the curated public SIMBAD table.
 */
import { raDecToMollweide } from "./mollweide";

const SVG_NS = "http://www.w3.org/2000/svg";

export function createSvgEl<K extends keyof SVGElementTagNameMap>(
  name: K,
): SVGElementTagNameMap[K] {
  return document.createElementNS(SVG_NS, name);
}

/** Closed Mollweide horizon (limb of the projected sphere). */
export function mollweideLimbPath(width: number, height: number): string {
  const pts: string[] = [];
  // Parametric limb: x = ±2√2 cosθ, y = √2 sinθ in normalized mollweide
  const n = 128;
  for (let i = 0; i <= n; i++) {
    const t = Math.PI * (-0.5 + i / n); // -pi/2 .. pi/2
    const xNorm = 2 * Math.SQRT2 * Math.cos(t);
    const yNorm = Math.SQRT2 * Math.sin(t);
    const x = ((xNorm / (2 * Math.SQRT2) + 1) / 2) * width;
    const y = ((1 - yNorm / Math.SQRT2) / 2) * height;
    pts.push(`${i === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`);
  }
  for (let i = n; i >= 0; i--) {
    const t = Math.PI * (-0.5 + i / n);
    const xNorm = -2 * Math.SQRT2 * Math.cos(t);
    const yNorm = Math.SQRT2 * Math.sin(t);
    const x = ((xNorm / (2 * Math.SQRT2) + 1) / 2) * width;
    const y = ((1 - yNorm / Math.SQRT2) / 2) * height;
    pts.push(`L${x.toFixed(2)} ${y.toFixed(2)}`);
  }
  pts.push("Z");
  return pts.join(" ");
}

export function projectRing(
  ring: number[][],
  width: number,
  height: number,
): string {
  const pts: string[] = [];
  for (const pair of ring) {
    const p = raDecToMollweide(Number(pair[0]), Number(pair[1]), width, height);
    if (p) pts.push(`${p.x.toFixed(1)},${p.y.toFixed(1)}`);
  }
  return pts.join(" ");
}

export function projectPolyline(
  ring: number[][],
  width: number,
  height: number,
): string {
  // Break on large jumps (RA wrap / projection discontinuity).
  const parts: string[] = [];
  let d = "";
  let prev: { x: number; y: number } | null = null;
  for (const pair of ring) {
    const p = raDecToMollweide(Number(pair[0]), Number(pair[1]), width, height);
    if (!p) {
      prev = null;
      continue;
    }
    if (!prev) {
      d += `M${p.x.toFixed(1)} ${p.y.toFixed(1)}`;
    } else {
      const jump = Math.hypot(p.x - prev.x, p.y - prev.y);
      if (jump > Math.min(width, height) * 0.25) {
        if (d) parts.push(d);
        d = `M${p.x.toFixed(1)} ${p.y.toFixed(1)}`;
      } else {
        d += `L${p.x.toFixed(1)} ${p.y.toFixed(1)}`;
      }
    }
    prev = p;
  }
  if (d) parts.push(d);
  return parts.join("");
}

/** Equatorial grid from public spherical coordinates (RA/Dec). */
export function drawEquatorialGrid(
  parent: SVGElement,
  width: number,
  height: number,
): void {
  const g = createSvgEl("g");
  g.setAttribute("class", "sky-grid");
  for (let ra = 0; ra < 360; ra += 30) {
    const ring: number[][] = [];
    for (let dec = -90; dec <= 90; dec += 3) ring.push([ra, dec]);
    const path = createSvgEl("path");
    path.setAttribute("d", projectPolyline(ring, width, height));
    path.setAttribute("class", "sky-grid-line");
    g.appendChild(path);
  }
  for (let dec = -60; dec <= 60; dec += 30) {
    const ring: number[][] = [];
    for (let ra = 0; ra <= 360; ra += 3) ring.push([ra % 360, dec]);
    const path = createSvgEl("path");
    path.setAttribute("d", projectPolyline(ring, width, height));
    path.setAttribute("class", "sky-grid-line");
    g.appendChild(path);
  }
  parent.appendChild(g);
}
