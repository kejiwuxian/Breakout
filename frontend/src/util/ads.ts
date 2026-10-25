/** ADS abstract URL from a real bibcode (never invent bibcodes). */
export function adsUrl(bibcode: string): string {
  return `https://ui.adsabs.harvard.edu/abs/${encodeURIComponent(bibcode)}/abstract`;
}
