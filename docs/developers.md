# Developer setup

Internal package and module names remain `breakout` (Python paths, env flags,
schema ids). The public product name is **Project Supernova** — see the root
[`README.md`](../README.md).

Honesty rules: never invent numbers or bibcodes; label every simulated value
(`simulated=true` in JSON; Simulated badge in the UI).

## Quick start

```bash
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn backend.app:app --reload          # idle / listening — no auto scenario
npm --prefix frontend install && npm --prefix frontend run dev         # :5173 primary
# optional parallel copy:
npm --prefix frontend-v2 install && npm --prefix frontend-v2 run dev   # :5174
```

Typical local API env:

```bash
USE_CACHED_STREAM=True VOICE_MODE=off uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

## Offline / scenarios

Offline capability (`USE_CACHED_STREAM=True`): fixtures under `data/cache/` are
available, with **no network** on the trigger path — but scenarios do **not**
auto-play. Cold start is idle / listening (hello `scenario=live_waiting`); use
the UI **Replay** rail or `POST /scenario/{name}/start` to inject simulated
events. Opt-in auto-replay only with `BREAKOUT_AUTOSTART=1`. Keys may stay empty.

```bash
# Manual simulated scenario
curl -X POST 'http://127.0.0.1:8000/scenario/scenario_a_galactic_ccsn/start?speed=0'

# Opt-in auto-replay (not default)
BREAKOUT_AUTOSTART=1 uvicorn backend.app:app --reload
```

## Skymap (post-#35)

Pure SVG Mollweide:

- **Background field** = Yale Bright Star Catalogue 5th Ed. (Hoffleit+1991 /
  CDS V/50 / NASA HEASARC BSC5P), V≤6.5, ~8.4k stars —
  `data/stars/sky_background.json`. Rebuild:
  `python scripts/build_sky_background_catalog.py`.
- **Ranked overlay** = curated inventory ∪ AOI-filtered BSC5 (pure red,
  magnitude-matched radius; outer AOI aperture; dual translucent red outlines).
- No galactic-plane line; no default Betelgeuse auto-select.
- Wheel zoom + drag pan; auto zoom to the localization oval on event.

## Subscribe to events (Phase 1)

**UI:** primary `frontend/` (`:5173`) rail **Subscribe to events** —
**access + refresh** tokens over WebSocket, honesty note, link to
`/alerts/latest`. Optional parallel UI on `:5174`.

```bash
curl -X POST http://127.0.0.1:8000/subscribe \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@observatory.edu","label":"campus-0.3m"}'
# → access_token + refresh_token; open ws://127.0.0.1:8000/ws/subscribe?access_token=…
# Refresh: POST /subscribe/refresh {"refresh_token":"…"} then send the new access_token on the live WS.
curl http://127.0.0.1:8000/alerts/latest
```

Default live push is WebSocket (`/ws/subscribe`) with access + refresh tokens.
`NOTIFY_DRY_RUN=True` logs optional email mirrors (no SMTP). This is community
follow-up for potential counterparts, not a confirmed supernova detection
service. Full walkthrough: [`community-subscribe.md`](community-subscribe.md).

## Phase 1 / Phase 2 flags

MVP gate: `bash scripts/mvp_gate.sh` must print PASS. Phase 2 sponsor
integrations sit behind flags that default to **False** (`DROID_ENABLED`,
`CONVEX_ENABLED`, `APIFY_ENABLED`, `TIGER_ENABLED`). With every flag off the
core loop is unchanged (`tests/test_flags_off.py`).

Community alerts are in Phase 1. Packages are honest: `simulated=true` when
applicable, ADS bibcodes only when already on the candidate, and they are not
official GCN notices.

Post-gate feature index: [`post-mvp.md`](post-mvp.md) — idle live-waiting,
BSC5 all-sky SVG + outer-AOI ranking, progenitor inventory / enrich-replay
(CandidateScore v1.1), Subscribe (access + refresh over WebSocket),
DiffPointing / live channels, Apify behind flags.

## Layout

Backend is FastAPI (`backend/`); primary mission UI is Vite + TypeScript
(`frontend/`, port **5173**) with the Project Supernova design language.
Optional parallel copy: [`frontend-v2/README.md`](../frontend-v2/README.md)
(port 5174).

Env reference: [`.env.example`](../.env.example).

## Tests / gate

```bash
pytest
bash scripts/preflight.sh
bash scripts/mvp_gate.sh
```

## Useful rebuild commands

```bash
# Rebuild Yale BSC5 background field
python scripts/build_sky_background_catalog.py

# Rebuild progenitor inventory offline
python -m backend.progenitors refresh
python -m backend.progenitors status
# Materialize inventory-schema enrichment for every AOI-ranked replay star
python -m backend.progenitors enrich-replay
```

## Apify: star literature actor

Phase 2.3. Actor: `actors/breakout-star-literature/` (offline only).

- Set `APIFY_ENABLED=True`, `APIFY_TOKEN`, and `APIFY_ACTOR_ID`, then either
  `python -m backend.integrations.apify_literature` or a live
  `python -m backend.literature.build_index` run (Apify runs before Grok scoring).
- Saves `data/index/apify/<star_id>.json`. `build_index.py` adds those items to
  what Grok reads, resolves each through the ADS API, and **drops any without a bibcode**.
- Local Actor check: `cd actors/breakout-star-literature && apify run` (3-star `INPUT.json`).
- With `APIFY_ENABLED=False` (default) the MVP never imports `apify_client` and the core loop is unchanged.

## Cursor + Grok Bot notes

- Cursor's agent builds modules from the plan Page; conventions live in
  `.cursor/rules/astro-conventions.mdc`.
- Prompt history: [`prompt-log.md`](prompt-log.md).
- Planning and team coordination: Grok Bot (plan Page + check-ins).
- **Grok Voice** announcer and spoken judge Q&A (SpaceXAI Make it Legendary).

## Team

| Person | Role |
| --- | --- |
| Light | Backend pipeline + voice backend |
| Tony | Ranking + dashboard + voice frontend |
| Vincent | Literature index content |
| Barron | Story + submission |

## Docs map

| Doc | Topic |
| --- | --- |
| [`post-mvp.md`](post-mvp.md) | Post-gate feature index |
| [`community-subscribe.md`](community-subscribe.md) | Subscribe UI + API |
| [`schemas.md`](schemas.md) | CandidateScore v1.1 |
| [`BREAKOUT_judge_science_QA.md`](BREAKOUT_judge_science_QA.md) | Judge Q&A |
| [`evidence/README.md`](evidence/README.md) | Demo checklist |
| [`../frontend-v2/README.md`](../frontend-v2/README.md) | v2 UI runbook |
