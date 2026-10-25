# Agent notes

## Cursor Cloud specific instructions

- **Local preview must always run the latest code under test.** After any code change, restart backend `:8000` and primary frontend `:5173` from the worktree/branch being changed. Do not leave stale `uvicorn`/`vite` processes pointing at an old worktree or branch. Kill stale listeners by PID only (never `pkill -f`).
- **Primary UI** is `frontend/` on `http://127.0.0.1:5173` (Supernova redesign; optional `frontend-v2` on `:5174`).
- **API** is `uvicorn backend.app:app` on `http://127.0.0.1:8000` (typical env: `USE_CACHED_STREAM=True VOICE_MODE=off BREAKOUT_DISABLE_AUTOSTART=0`).
- **Public demo** origin is `https://supernova.lylinks.com` (`BREAKOUT_PUBLIC_BASE_URL` / `bash scripts/run_public.sh` + gitignored `CLOUDFLARE_TUNNEL_TOKEN`).
- **Skymap truth (post-#35):** background = Yale BSC5 (`/api/sky/base`); ranked overlay = curated ∪ outer-AOI BSC5; dual red AOI (outer translucent); no galactic-plane line; no default Betelgeuse select; `UNK` breakout is `n/a`.
- **Subscribe truth:** rail title **Subscribe to events**; `POST /subscribe` (empty OK) → access + refresh → `/ws/subscribe`.
