/** ADS abstract page for a bibcode (never invent bibcodes — only link given ones). */
export function adsUrl(bibcode: string): string {
  return `https://ui.adsabs.harvard.edu/abs/${encodeURIComponent(bibcode)}`;
}
