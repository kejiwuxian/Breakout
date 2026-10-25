# BREAKOUT frontend-v2

Redesigned mission UI for the same product and backend as `frontend/`.
**Does not replace the classic dashboard** — run both side by side if you want.

## Design intent

- One composition: skymap as the dominant visual plane; controls on a side rail
- Brand-first: **BREAKOUT** is the hero signal
- Expressive type: Syne + IBM Plex Sans / Mono
- Atmospheric night field (gradients + sparse star dust), not a flat fill
- Interactive localization: **pure SVG** Mollweide (curated progenitor catalog stars + galactic plane + HEALPix cells); on an event, a **smooth red oval** appears and the view **zooms the same SVG** (no raster swap). **Wheel zoom**, **drag pan**, double-click / Full sky reset. Hover ranked stars for posterior, confidence, life window, composition.
- Field stars are **not** a uniform all-sky survey — they are the curated SN-progenitor list. The dashed line is the **galactic plane**.
- Simulated / Real badges preserved; no invented numbers or citations
- Motion: brand letter-spacing settle, rail rise, skymap fade-in (reduced-motion safe)

## Run

Backend (same as classic):

```bash
USE_CACHED_STREAM=True VOICE_MODE=off python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Cold start is **idle / listening** (no auto Scenario A). The stream shows live + waiting for neutrino alerts; empty ranked list and public-catalog full sky until a live alert arrives or you click **Run** on Replay. Cached mode is offline capability, not auto-play. Optional: open with `?hydrate=1` to seed from a prior `/alerts/latest` package.

This UI (port **5174**):

```bash
npm --prefix frontend-v2 install
npm --prefix frontend-v2 run dev
```

Open http://127.0.0.1:5174 — classic UI remains on http://127.0.0.1:5173.

## Community push

The rail **Community push** block uses the two-token email flow
(`POST /subscribe/request` → confirm tokens → `POST /subscribe/confirm`).
No webhook fields. Default `NOTIFY_DRY_RUN=True` returns Simulated/dry-run
tokens in the API response for local demos (no invented SMTP). Packages carry
`simulated=true` when applicable and are not official GCN notices. Details:
[`docs/community-subscribe.md`](../docs/community-subscribe.md).
