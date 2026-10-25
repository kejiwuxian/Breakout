/**
 * Lazy-load Aladin Lite v3 for a real DSS/HiPS sky background.
 * Falls back cleanly when CDN/network is unavailable (offline demo).
 */

export type AladinApi = {
  aladin: (
    el: string | HTMLElement,
    opts?: Record<string, unknown>,
  ) => AladinInstance;
  graphicOverlay: (opts?: { color?: string; lineWidth?: number }) => GraphicOverlay;
  polygon: (raDec: number[][], opts?: { color?: string; lineWidth?: number }) => unknown;
  catalog: (opts?: Record<string, unknown>) => Catalog;
  source: (
    ra: number,
    dec: number,
    data?: Record<string, unknown>,
  ) => CatalogSource;
};

export type AladinInstance = {
  gotoRaDec: (ra: number, dec: number) => void;
  setFov: (fovDeg: number) => void;
  removeLayers: () => void;
  addOverlay: (overlay: GraphicOverlay) => void;
  addCatalog: (catalog: Catalog) => void;
  on: (event: string, cb: (obj: CatalogSource | null) => void) => void;
  destroy?: () => void;
};

export type GraphicOverlay = {
  addFootprints: (fps: unknown[]) => void;
};

export type Catalog = {
  addSources: (sources: CatalogSource[] | CatalogSource) => void;
};

export type CatalogSource = {
  data?: Record<string, unknown>;
  ra?: number;
  dec?: number;
};

declare global {
  interface Window {
    A?: AladinApi;
  }
}

const ALADIN_JS =
  "https://aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.js";

let loading: Promise<AladinApi> | null = null;

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      `script[data-breakout-aladin="1"]`,
    );
    if (existing && window.A) {
      resolve();
      return;
    }
    const s = document.createElement("script");
    s.src = src;
    s.async = true;
    s.dataset.breakoutAladin = "1";
    s.onload = () => resolve();
    s.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(s);
  });
}

/** Load Aladin Lite; rejects if CDN unreachable (caller uses SVG fallback). */
export async function loadAladin(timeoutMs = 8000): Promise<AladinApi> {
  if (window.A?.aladin) return window.A;
  if (!loading) {
    loading = (async () => {
      const timer = new Promise<never>((_, reject) => {
        window.setTimeout(
          () => reject(new Error("Aladin load timeout")),
          timeoutMs,
        );
      });
      await Promise.race([loadScript(ALADIN_JS), timer]);
      if (!window.A?.aladin) throw new Error("Aladin global A missing");
      return window.A;
    })().catch((err) => {
      loading = null;
      throw err;
    });
  }
  return loading;
}
