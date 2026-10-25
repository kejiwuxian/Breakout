# Project Supernova — SpaceX track UI

Separate frontend themed after SpaceX.com / launch webcast chrome (black stage,
white type, LIVE lower-thirds, telemetry rail). Same APIs as the primary
mission UI.

| | |
| --- | --- |
| **Production** | `https://supernova.lylinks.com/spacex/` |
| **Local Vite** | `npm --prefix frontend-spacex run dev` → `:5175` (base `/spacex/`) |
| **Build** | `npm --prefix frontend-spacex run build` → `frontend-spacex/dist` |

FastAPI serves the build at `/spacex` when `BREAKOUT_SERVE_FRONTEND=1` (see
`scripts/run_public.sh`).
