# BREAKOUT frontend-v2

Redesigned mission UI for the same product and backend as `frontend/`.
**Does not replace the classic dashboard** — run both side by side if you want.

## Design intent

- One composition: skymap as the dominant visual plane; controls on a side rail
- Brand-first: **BREAKOUT** is the hero signal
- Expressive type: Syne + IBM Plex Sans / Mono
- Atmospheric night field (gradients + sparse star dust), not a flat fill
- Simulated / Real badges preserved; no invented numbers or citations
- Motion: brand letter-spacing settle, rail rise, skymap fade-in (reduced-motion safe)

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
