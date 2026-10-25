# After MVP gate — feature index

Public product name: **Project Supernova** (internal packages still `breakout`).
Story README: [`../README.md`](../README.md). Developer setup:
[`developers.md`](developers.md).

`scripts/mvp_gate.sh` printed **PASS**. Everything below landed on `main` after that
gate (including the post-merge stack through **#35**). Honesty rules unchanged:
never invent numbers/bibcodes; label `simulated=true`.

## Product surface

| Area | What it does | Where |
| --- | --- | --- |
| **Idle / live waiting** | Cold start does **not** auto-play Scenario A. Hello uses `scenario=live_waiting`; UI shows listening + empty candidates + BSC5 full sky until a live alert or manual Replay. | `backend/app.py`, `BREAKOUT_AUTOSTART` (opt-in), frontend `?hydrate=1` |
| **frontend (primary)** | Project Supernova redesigned mission UI on **:5173**. | `frontend/` |
| **SVG skymap** | Pure SVG Mollweide: Yale BSC5 all-sky field (V≤6.5) + curated-inventory ranked overlay; dual size-based red AOI outlines (outer translucent); no galactic-plane polyline. | `backend/localize/region.py`, `frontend/src/panels/sky.ts`, `data/stars/sky_background.json` |
| **AOI ranking** | Membership uses the **outer** AOI aperture (credible ∪ peak-ring); curated progenitors ∪ BSC5 field (UNK capped); shared Vmag radius/opacity; pure `#ff0000` rank opacity; no default Betelgeuse auto-select. | `backend/candidates/filter.py`, `catalog.py`, `scripts/aoi_outer_verify.mjs` |
| **Zoom / pan** | Auto zoom-to-AOI on event; mouse wheel zoom; drag pan; double-click / reset to full sky. | `frontend/src/panels/sky.ts` |
| **Progenitor inventory** | Offline inventory of SN-potential stars (position, composition, class life window, confidence). Runtime AOI filter + `rank_with_grok` (offline when cached / no key). | `backend/progenitors/`, CandidateScore **v1.1** |
| **Replay enrichment** | `python -m backend.progenitors enrich-replay` → `replay_rank_enrichment.parquet`; field stars get SpType composition / parallax / conf without cloning RSG life onto `UNK`. | `backend/progenitors/enrich.py`, `data/stars/replay_rank_enrichment.parquet` |
| **Subscribe to events** | Open access + refresh tokens over **`/ws/subscribe`** (auto-close on access expiry); `/alerts/latest` feed. No account / prior credentials. | `backend/notify/`, frontend **Subscribe to events** rail |
| **DiffPointing + live channels** | SNEWS-style timing localization; public GCN/Hopskotch subscriptions when `USE_CACHED_STREAM=False`. | `backend/localize/snews_diffpointing.py`, `backend/ingest/live_channels.py` |
| **Actions + Voice** | LCOGT/ToO/GCN drafts; Grok Voice announcer + judge tools. | `backend/actions/`, `backend/voice/` |
| **Apify literature (P2.3)** | Optional offline actor behind `APIFY_ENABLED=False` by default. | `actors/breakout-star-literature/`, `backend/integrations/apify_literature.py` |

## Skymap honesty

- **Background field** = Yale Bright Star Catalogue 5th Ed. (Hoffleit+1991 / CDS V/50 / NASA HEASARC BSC5P), magnitude-limited **V≤6.5** (~8.4k stars) in `data/stars/sky_background.json`. Rebuild: `python scripts/build_sky_background_catalog.py`.
- **Ranked overlay** = curated progenitor inventory ∪ AOI-filtered BSC5 hits. Pure red markers use the same magnitude radius/opacity as the field; hover shows posterior, confidence, life window, composition.
- **AOI** = dual red outlines sized by projected geometry; the **outer** mark (often a peak ring for IceCube-scale ellipses) drives ranking membership. No dashed galactic-plane line; `galactic_plane` payloads are empty.
- **Selection** = no auto-select of the top candidate (Betelgeuse or otherwise) on scenario start.

## Life expectancy / CONF

Inventory `life_expectancy.optical_breakout_window` is a **class** optical-breakout estimate (minutes / hours / about 1 day), not a star-specific collapse countdown. `UNK` field stars (no clear RSG/BSG/YSG/WR/LBV) keep breakout **`n/a`** — they do **not** inherit RSG life windows. `stellar_stage_note` appears only when an ADS claim already supports it. UI **Conf** comes from `rank_confidence` / literature confidence.

## Useful commands

```bash
# Idle API (no auto scenario)
uvicorn backend.app:app --host 127.0.0.1 --port 8000

# Mission UI (primary)
npm --prefix frontend run dev      # :5173

# Rebuild Yale BSC5 background field
python scripts/build_sky_background_catalog.py

# Rebuild progenitor inventory offline
python -m backend.progenitors refresh
python -m backend.progenitors status
# Materialize inventory-schema enrichment for every AOI-ranked replay star
# (Yale BSC5 SpType → composition / life window; no live Grok required)
python -m backend.progenitors enrich-replay

# Manual simulated scenario
curl -X POST 'http://127.0.0.1:8000/scenario/scenario_a_galactic_ccsn/start?speed=0'

# Opt-in auto-replay (not default)
BREAKOUT_AUTOSTART=1 uvicorn backend.app:app --reload
```

## Docs map

| Doc | Topic |
| --- | --- |
| [`developers.md`](developers.md) | Setup, ports, env, scenarios, gate |
| [`community-subscribe.md`](community-subscribe.md) | Subscribe UI + API |
| [`schemas.md`](schemas.md) | CandidateScore v1.1 |
| [`BREAKOUT_judge_science_QA.md`](BREAKOUT_judge_science_QA.md) | Judge Q&A |
| [`evidence/README.md`](evidence/README.md) | Demo checklist |
| [`../frontend/README.md`](../frontend/README.md) | Primary UI runbook |
| [`.env.example`](../.env.example) | Flags and keys |
