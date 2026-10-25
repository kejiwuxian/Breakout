# Project Supernova — frontend

Primary mission UI on port **5173**. Product flows come from the former
`frontend-v2` experience (skymap, ranked progenitors, Subscribe to events,
replay, idle/live); visuals follow the Project Supernova design language
(deep blue workstation, mint signal, Syne + IBM Plex).

## Run

```bash
USE_CACHED_STREAM=True VOICE_MODE=off python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
npm --prefix frontend install
npm --prefix frontend run dev
```

Open http://127.0.0.1:5173

Cold start is **idle / listening** (no auto Scenario A). Optional
`?hydrate=1` seeds from a prior `/alerts/latest` package.

## Layout

- Top nav: brand → About (`#/about`) → stream status, Simulated / Historical / Live badges
- Main: page chrome → SVG Mollweide skymap → event select cards
- Rail: event summary → ranked objects → detail/evidence → Subscribe → voice
- About: hash route `#/about`; brand / Back to mission returns to `#/`

Skymap behavior (BSC5 field, dual AOI, ranked red stars, wheel zoom / pan)
matches the previous v2 panel; chrome uses design tokens (AOI red retained
for science meaning).

The optional `frontend-v2/` tree remains a parallel copy on **5174** for
comparison; **5173 is the product entry**.
