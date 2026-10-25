/**
 * Simple gnomonic-style projection for offline SVG fallback.
 * Coordinates are ICRS degrees; origin at the localization peak.
 */

export function raDecToFocusPx(
  raDeg: number,
  decDeg: number,
  peakRa: number,
  peakDec: number,
  fovDeg: number,
  width: number,
  height: number,
): { x: number; y: number } | null {
  const cosDec0 = Math.max(Math.cos((peakDec * Math.PI) / 180), 0.15);
  let dRa = ((raDeg - peakRa + 540) % 360) - 180;
  dRa *= cosDec0;
  const dDec = decDeg - peakDec;
  const half = fovDeg / 2;
  if (Math.abs(dRa) > half * 1.35 || Math.abs(dDec) > half * 1.35) {
    // Still plot near-edge stars; clamp rather than drop.
  }
  const x = width / 2 + (dRa / fovDeg) * width;
  const y = height / 2 - (dDec / fovDeg) * height;
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { x, y };
}
