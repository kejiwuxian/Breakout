# BREAKOUT

Neutrino-first supernova interceptor for **Cal Hacks 13.0**, SpaceXAI **Make it Legendary** track.

When the next galactic supernova goes off, neutrinos reach Earth first. BREAKOUT fuses detector signals into a sky map, ranks likely progenitors from a precomputed literature index, and drafts telescope requests before optical breakout.

## Built with Cursor + Grok Bot

- Cursor's agent builds modules from the plan Page; conventions live in `.cursor/rules/astro-conventions.mdc`.
- Prompt history: `docs/prompt-log.md`.
- Planning and team coordination: Grok Bot (plan Page + check-ins).
- **Grok Voice** announcer and spoken judge Q&A (required for Make it Legendary).

## Phase 1 / Phase 2

MVP gate: `bash scripts/mvp_gate.sh` must print PASS. Phase 2 sponsor integrations sit behind flags that default to **False** (`DROID_ENABLED`, `CONVEX_ENABLED`, `APIFY_ENABLED`, `TIGER_ENABLED`). With every flag off the core loop is unchanged (`tests/test_flags_off.py`).

**Community alerts are in Phase 1.** Anyone with a telescope can subscribe today for ranked progenitor coordinates when BREAKOUT localizes a neutrino burst — so small instruments can chase a potential optical counterpart before large facilities respond. Packages are honest: `simulated=true` when applicable, ADS bibcodes only when already on the candidate, and they are not official GCN notices.

## After MVP gate

Full post-gate index: [`docs/post-mvp.md`](docs/post-mvp.md) — idle live-waiting default, SVG skymap zoom/pan, progenitor inventory (CandidateScore v1.1), two-token community push, DiffPointing / live channels, Apify behind flags.

## Quick start

```bash
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn backend.app:app --reload          # idle / listening — no auto scenario
npm --prefix frontend-v2 install && npm --prefix frontend-v2 run dev   # :5174
# optional classic UI:
npm --prefix frontend install && npm --prefix frontend run dev         # :5173
```

Offline capability (`USE_CACHED_STREAM=True`): fixtures under `data/cache/` are available, with **no network** on the trigger path — but scenarios do **not** auto-play. Cold start is idle / listening (hello `scenario=live_waiting`); use the UI **Replay** rail or `POST /scenario/{name}/start` to inject simulated events. Opt-in auto-replay only with `BREAKOUT_AUTOSTART=1`. Keys may stay empty. Label every simulated number (`simulated=true` in JSON; Simulated badge in the UI).

**Skymap:** pure SVG Mollweide; field stars are the curated progenitor catalog (not a uniform all-sky survey); dashed line = galactic plane; wheel zoom + drag pan; auto zoom to the localization oval on event.

## Community alerts (Phase 1) — catch potential SNe today

**UI:** frontend-v2 (`:5174`) rail **Community push**, or the classic dashboard (`:5173`) **Community alerts** panel — **two-token email** confirm (no webhook), status line, honesty note, link to `/alerts/latest`.

Confirm an email, then receive ranked ICRS targets by email on the next SN_BURST / HE_NEUTRINO candidate set:

```bash
curl -X POST http://127.0.0.1:8000/subscribe/request \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@observatory.edu","label":"campus-0.3m"}'
# dry-run returns request_token + confirm_token under dry_run — then:
curl -X POST http://127.0.0.1:8000/subscribe/confirm \
  -H 'Content-Type: application/json' \
  -d '{"request_token":"…","confirm_token":"…"}'
curl http://127.0.0.1:8000/alerts/latest
```

Default `NOTIFY_DRY_RUN=True` returns Simulated/dry-run tokens in the API and logs alert emails (no SMTP). Only confirmed subscribers are emailed. This is community follow-up for potential counterparts, not a confirmed supernova detection service. Full walkthrough: [`docs/community-subscribe.md`](docs/community-subscribe.md).

## Layout

See the plan Page **Repo layout** section. Backend is FastAPI (`backend/`); classic dashboard is Vite + TypeScript (`frontend/`, port 5173). Redesigned mission UI lives in **`frontend-v2/`** (port 5174) — same APIs, separate app; see `frontend-v2/README.md`.

## Tests / gate

```bash
pytest
bash scripts/preflight.sh
bash scripts/mvp_gate.sh
```

## Team

| Person | Role |
| --- | --- |
| Light | Backend pipeline + voice backend |
| Tony | Ranking + dashboard + voice frontend |
| Vincent | Literature index content |
| Barron | Story + submission |

## Apify: star literature actor

Phase 2.3 (Vincent). Actor: `actors/breakout-star-literature/` (from
`apify create … --template python-start`, Cal Hacks 13.0).

- **Offline only.** Set `APIFY_ENABLED=True`, `APIFY_TOKEN`, and `APIFY_ACTOR_ID`, then either
  `python -m backend.integrations.apify_literature` or a live
  `python -m backend.literature.build_index` run (Apify runs before Grok scoring).
- Saves `data/index/apify/<star_id>.json`. `build_index.py` adds those items to
  what Grok reads, resolves each through the ADS API, and **drops any without a bibcode**.
- Local Actor check: `cd actors/breakout-star-literature && apify run` (3-star `INPUT.json`).
- With `APIFY_ENABLED=False` (default) the MVP never imports `apify_client` and the core loop is unchanged.
