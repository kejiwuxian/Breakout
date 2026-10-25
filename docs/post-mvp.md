# After MVP gate

`scripts/mvp_gate.sh` printed **PASS** on the offline Phase 1 path. Work below landed afterward (or was locked into Phase 1 claim language late). This page indexes those modules so demos and judges can find them without inventing capabilities.

Honesty rules still apply everywhere: never invent numbers or ADS bibcodes; label simulated values with `simulated=true` / Simulated badges; community packages are **not** official GCN notices.

## Feature index

| Feature | Where | Notes |
| --- | --- | --- |
| Community notify | `backend/notify/`, `POST /subscribe`, `GET /alerts/latest`, `data/subscribers/` | Ranked ICRS targets for SN_BURST / HE_NEUTRINO; `NOTIFY_DRY_RUN=True` by default |
| Interactive SVG skymap | `backend/localize/region.py`, `GET /api/sky/base`, `GET /api/skymap/{id}/region`, `frontend-v2/src/panels/sky.ts` | Full-sky Mollweide by default; CSS zoom of the **same** SVG; smooth 90% oval; hover posteriors |
| Skymap field stars | curated `data/stars/curated_stars.json` via `load_public_field_stars` | **Curated progenitors**, not a uniform all-sky catalog |
| Galactic plane guide | dashed path from Astropy `b=0` → ICRS | Visual guide only |
| Evidence panel (no flash) | `literature/build_index.ensure_raw_for_star`, `/api/literature/raw` | Materializes offline raw JSON from fixtures or `index.parquet` |
| Progenitors inventory | `backend/progenitors/`, `GET /api/progenitors/inventory` | Offline 41-star inventory + publication monitor + `rank_with_grok` |
| CandidateScore v1.1 | `backend/schemas.py`, `docs/schemas.md` | Additive: `rank_confidence`, `rank_reasoning`, `life_expectancy`, `composition` |
| SNEWS DiffPointing | `backend/localize/snews_diffpointing.py` + fuse | Joint-χ² timing when ≥2 long baselines; else legacy rings / pointing |
| Live public channels | `backend/ingest/live_channels.py` | SNEWS2 coincidence, classic SNEWS, IceCube gold/bronze, pre-SN; optional Hopskotch |
| IceCube scenarios | `data/cache/scenario_b_*`, `scenario_c_*`, `scenario_d_*`, `icecube_alert_catalog/` | Historical HE_NEUTRINO replays; Real-data badges where `simulated=false` |
| Actions drafts | `backend/actions/` | LCOGT dry-run RequestGroup, HST/JWST ToO Markdown, GCN Circular **DRAFT** |
| Grok Voice | `backend/voice/`, frontend(+v2) voice panels | Announcer TTS + judge PTT tools (`VOICE_MODE=live\|cached\|off`) |
| frontend-v2 | `frontend-v2/` port **5174** | Redesigned mission UI; classic dashboard stays on **5173** |

## Quick commands

```bash
# Mission UI (post-MVP demo surface)
USE_CACHED_STREAM=True VOICE_MODE=off uvicorn backend.app:app --host 127.0.0.1 --port 8000
npm --prefix frontend-v2 install && npm --prefix frontend-v2 run dev   # :5174

# Community alerts
curl -X POST http://127.0.0.1:8000/subscribe \
  -H 'Content-Type: application/json' \
  -d '{"webhook_url":"https://your.site/hook","label":"campus-0.3m"}'
curl http://127.0.0.1:8000/alerts/latest

# Progenitor inventory CLI
python -m backend.progenitors refresh
python -m backend.progenitors status
python -m backend.progenitors monitor --dry-run
curl http://127.0.0.1:8000/api/progenitors/inventory

# Live ingest (needs GCN keys; trigger path offline when USE_CACHED_STREAM=True)
# USE_CACHED_STREAM=False  →  DiffPointing / pointing / optional healpix_url
```

## Skymap honesty

- Default view is **full sky** (SVG Mollweide).
- On an event, a **smooth red oval** marks the probability-weighted 90% localization ellipse; the view zooms that same SVG (no raster swap in frontend-v2).
- Background dots are **curated progenitor-catalog stars**, not every star in the sky.
- The **dashed curve** is the **galactic plane** (`b=0`), not an orbit or trajectory.
- Classic UI may still use Mollweide PNG / `/focus.png`; frontend-v2 prefers pure SVG (`render=svg_v1`).

## Ranking honesty (inventory)

- `life_expectancy` is a **class optical-breakout window** (WR → minutes, BSG/YSG/LBV → hours, RSG → about 1 day), not a star-specific collapse countdown.
- `stellar_stage_note` appears only when copied from an existing ADS claim.
- `rank_confidence` / `rank_reasoning` come from offline inventory enrichment, or live Grok shortlist rank when keys allow; offline/deterministic when `USE_CACHED_STREAM` or no key.
- No invented bibcodes.

## Related docs

- Root overview: [`README.md`](../README.md)
- Schemas: [`schemas.md`](schemas.md)
- Prompt / agent log: [`prompt-log.md`](prompt-log.md)
- Demo evidence checklist: [`evidence/README.md`](evidence/README.md)
- Judge science Q&A: [`BREAKOUT_judge_science_QA.md`](BREAKOUT_judge_science_QA.md)
- frontend-v2: [`../frontend-v2/README.md`](../frontend-v2/README.md)
- Community subscribers: [`../data/subscribers/README.md`](../data/subscribers/README.md)
