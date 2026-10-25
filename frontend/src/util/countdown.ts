/** Breakout countdown display; "n/a" skips the clock for non-stellar sources. */
export function isBreakoutSkipped(classWindow: string): boolean {
  return classWindow === "n/a" || classWindow === "";
}

export function formatElapsed(fromIso: string, nowMs = Date.now()): string {
  const t0 = Date.parse(fromIso);
  if (!Number.isFinite(t0)) return "—";
  const sec = Math.max(0, Math.floor((nowMs - t0) / 1000));
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export function windowLabel(classWindow: string): string {
  if (isBreakoutSkipped(classWindow)) return "—";
  return classWindow;
}
