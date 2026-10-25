# Runtime output (`data/run/`)

Per-alert directories are written here at runtime and are **gitignored**:

- `skymap.fits` — fused HEALPix map
- `skymap.png` — Mollweide 2D fallback
- `lcogt_request.json` — dry-run RequestGroup
- `voice/` — announcer audio for this alert

Do not commit secrets or live API responses here.
