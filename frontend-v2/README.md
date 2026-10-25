# BREAKOUT frontend-v2

Redesigned mission UI for the same product and backend as `frontend/`.
**Does not replace the classic dashboard** — run both side by side if you want.

## Design intent

- One composition: skymap as the dominant visual plane; controls on a side rail
- Brand-first: **BREAKOUT** is the hero signal
- Expressive type: Syne + IBM Plex Sans / Mono
- Atmospheric night field (gradients + sparse star dust), not a flat fill
- Interactive localization: **pure SVG** Mollweide; on an event, a **smooth red oval** appears and the view **zooms the same SVG** (no raster swap). Hover ranked stars for posterior / `p_sky` (and CONF / life / composition when the inventory path fills v1.1 fields).
- Simulated / Real badges preserved; no invented numbers or citations
- Motion: brand letter-spacing settle, rail rise, skymap fade-in (reduced-motion safe)

## Skymap layers (honesty)

| Layer | Meaning |
| --- | --- |
| Field stars | **Curated progenitor catalog** (`data/stars/curated_stars.json`) — not a uniform all-sky survey |
| Dashed curve | **Galactic plane** (`b=0` via Astropy → ICRS) |
| HEALPix cells | Probability mass inside the 90% region (when an alert is active) |
| Red oval | Smooth 90% localization ellipse from the fused map |
| Ranked markers | Pipeline candidates; hover shows scores already on the candidate |

Endpoints: `GET /api/sky/base` (no alert), `GET /api/skymap/{alert_id}/region` (SVG layers). Classic UI may still use Mollweide PNG / `/focus.png`.

## Run

Backend (same as classic):

```bash
USE_CACHED_STREAM=True VOICE_MODE=off python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

This UI (port **5174**):

```bash
npm --prefix frontend-v2 install
npm --prefix frontend-v2 run dev
```

Open http://127.0.0.1:5174 — classic UI remains on http://127.0.0.1:5173.

Related: [`docs/post-mvp.md`](../docs/post-mvp.md).
