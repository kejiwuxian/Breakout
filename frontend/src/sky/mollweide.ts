/**
 * Approximate Mollweide projection matching healpy mollview PNGs.
 * Coordinates are ICRS degrees (RA, Dec).
 */
export function raDecToMollweide(
  raDeg: number,
  decDeg: number,
  width: number,
  height: number,
): { x: number; y: number } | null {
  const lon = ((((raDeg + 180) % 360) + 360) % 360) - 180;
  const lat = Math.max(-90, Math.min(90, decDeg));
  const lambda = (lon * Math.PI) / 180;
  const phi = (lat * Math.PI) / 180;

  let theta = phi;
  for (let i = 0; i < 12; i++) {
    const f = 2 * theta + Math.sin(2 * theta) - Math.PI * Math.sin(phi);
    const fp = 2 + 2 * Math.cos(2 * theta);
    if (Math.abs(fp) < 1e-12) break;
    theta -= f / fp;
  }

  const xNorm = ((2 * Math.SQRT2) / Math.PI) * lambda * Math.cos(theta);
  const yNorm = Math.SQRT2 * Math.sin(theta);
  const x = ((xNorm / (2 * Math.SQRT2) + 1) / 2) * width;
  const y = ((1 - yNorm / Math.SQRT2) / 2) * height;
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { x, y };
}
