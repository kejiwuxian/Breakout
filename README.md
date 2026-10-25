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


## Quick start

```bash
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn backend.app:app --reload
npm --prefix frontend install
npm --prefix frontend run dev
```

Offline capability (`USE_CACHED_STREAM=True`): fixtures under `data/cache/` are available, with **no network** on the trigger path — but scenarios do **not** auto-play. Cold start is idle / listening (hello `scenario=live_waiting`); use the UI **Replay** rail or `POST /scenario/{name}/start` to inject simulated events. Opt-in auto-replay only with `BREAKOUT_AUTOSTART=1`. Keys may stay empty. Label every simulated number (`simulated=true` in JSON; Simulated badge in the UI).

## Community alerts (Phase 1) — catch potential SNe today

**UI:** frontend-v2 (`:5174`) rail **Community push**, or the classic dashboard (`:5173`) **Community alerts** panel — webhook and/or email, status line, honesty note, link to `/alerts/latest`.

Subscribe a webhook (or optional email) and receive ranked ICRS targets on the next SN_BURST / HE_NEUTRINO candidate set:

```bash
curl -X POST http://127.0.0.1:8000/subscribe \
  -H 'Content-Type: application/json' \
  -d '{"webhook_url":"https://your.site/hook","label":"campus-0.3m"}'
curl http://127.0.0.1:8000/alerts/latest
```

Default `NOTIFY_DRY_RUN=True` logs deliveries; set `NOTIFY_DRY_RUN=False` to POST live webhook JSON. This is community follow-up for potential counterparts, not a confirmed supernova detection service. Full walkthrough: [`docs/community-subscribe.md`](docs/community-subscribe.md).

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

Phase 2.3 (Vincent). Actor source: `actors/breakout-star-literature/`.

- Offline only: set `APIFY_ENABLED=True` (and optionally `APIFY_TOKEN` + `APIFY_ACTOR_ID`) then run
  `python -m backend.integrations.apify_literature --curated-only --local`.
- Writes public ATel/arXiv discovery rows to `data/index/apify/<star>.json` with `simulated=false`.
- Does **not** invent citations; ranked claims still require ADS bibcodes in the MVP index builder.
- With `APIFY_ENABLED=False` (default) the MVP never imports or calls Apify.
