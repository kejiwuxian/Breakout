# After MVP gate — feature index

`scripts/mvp_gate.sh` printed **PASS**. Everything below landed on `main` after that
gate. Honesty rules unchanged: never invent numbers/bibcodes; label
`simulated=true`.

## Product surface

| Area | What it does | Where |
| --- | --- | --- |
| **Idle / live waiting** | Cold start does **not** auto-play Scenario A. Hello uses `scenario=live_waiting`; UI shows listening + empty candidates + public-catalog full sky until a live alert or manual Replay. | `backend/app.py`, `BREAKOUT_AUTOSTART` (opt-in), frontend-v2 `?hydrate=1` |
| **frontend-v2** | Redesigned mission UI on **:5174** (classic :5173 untouched). | `frontend-v2/` |
| **SVG skymap** | Pure SVG Mollweide: Yale BSC5 all-sky background, HEALPix cells, smooth localization oval (non-scaling red stroke + peak ring for tiny IceCube ellipses); ranked progenitors as pure-red overlays. | `backend/localize/region.py`, `frontend-v2/src/panels/sky.ts`, `data/stars/sky_background.json` |
| **Zoom / pan** | Auto zoom-to-AOI on event; mouse wheel zoom; drag pan; double-click / reset to full sky. | `frontend-v2/src/panels/sky.ts` |
| **Progenitor inventory** | Offline inventory of SN-potential stars (position, composition, class life window, confidence). Runtime AOI filter + `rank_with_grok` (offline when cached / no key). | `backend/progenitors/`, CandidateScore **v1.1** |
| **Community push** | Two-token email confirm (**no webhook**); only active subscribers get email; `/alerts/latest` feed. | `backend/notify/`, frontend-v2 **Community push** rail |
| **DiffPointing + live channels** | SNEWS-style timing localization; public GCN/Hopskotch subscriptions when `USE_CACHED_STREAM=False`. | `backend/localize/snews_diffpointing.py`, `backend/ingest/live_channels.py` |
| **Actions + Voice** | LCOGT/ToO/GCN drafts; Grok Voice announcer + judge tools. | `backend/actions/`, `backend/voice/` |
| **Apify literature (P2.3)** | Optional offline actor behind `APIFY_ENABLED=False` by default. | `actors/breakout-star-literature/`, `backend/integrations/apify_literature.py` |

## Skymap honesty

- **Background field stars** = Yale Bright Star Catalogue 5th Revised Ed. (Hoffleit & Warren 1991), CDS/VizieR ``V/50``, same edition as NASA HEASARC ``BSC5P``. Committed compact table: `data/stars/sky_background.json` (V ≤ 6.5, ~8.4k stars, full-sky RA/Dec). Served by `GET /api/sky/base`. Rebuild: `python scripts/build_sky_background_catalog.py`. Provenance/license: `data/stars/sky_background_meta.json`.
- **Ranked progenitor markers** = curated inventory / CandidateScore (`data/stars/curated_stars.json`, `progenitor_inventory.parquet`) — used for AOI filter + Grok ranking, drawn as pure-red overlays (rank opacity, same magnitude radius as field stars). Not the background field.
- No galactic-plane guide is drawn; `/api/sky/base` and region payloads return empty `galactic_plane`.
- Ranked markers get hover details (posterior, confidence, life window, composition); background stars get a light name/V/coords tip.

## Life expectancy / CONF

Inventory `life_expectancy.optical_breakout_window` is a **class** optical-breakout estimate (minutes / hours / about 1 day), not a star-specific collapse countdown. `stellar_stage_note` appears only when an ADS claim already supports it. UI **Conf** comes from `rank_confidence` / literature confidence.

## Useful commands

```bash
# Idle API (no auto scenario)
uvicorn backend.app:app --host 127.0.0.1 --port 8000

# Mission UI
npm --prefix frontend-v2 run dev   # :5174

# Rebuild progenitor inventory offline
python -m backend.progenitors refresh
python -m backend.progenitors status

# Rebuild all-sky SVG background (Yale BSC5 / HEASARC BSC5P)
python scripts/build_sky_background_catalog.py

# Manual simulated scenario
curl -X POST 'http://127.0.0.1:8000/scenario/scenario_a_galactic_ccsn/start?speed=0'

# Opt-in auto-replay (not default)
BREAKOUT_AUTOSTART=1 uvicorn backend.app:app --reload
```

## Docs map

| Doc | Topic |
| --- | --- |
| [`community-subscribe.md`](community-subscribe.md) | Subscribe UI + API |
| [`schemas.md`](schemas.md) | CandidateScore v1.1 |
| [`BREAKOUT_judge_science_QA.md`](BREAKOUT_judge_science_QA.md) | Judge Q&A |
| [`evidence/README.md`](evidence/README.md) | Demo checklist |
| [`../frontend-v2/README.md`](../frontend-v2/README.md) | v2 UI runbook |
| [`.env.example`](../.env.example) | Flags and keys |
