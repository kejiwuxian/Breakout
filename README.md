# BREAKOUT

Neutrino-first supernova interceptor for **Cal Hacks 13.0**, SpaceXAI **Make it Legendary** track.

When the next galactic supernova goes off, neutrinos reach Earth first. BREAKOUT fuses detector signals into a sky map, ranks likely progenitors from a precomputed literature index, and drafts telescope requests before optical breakout.

## Built with Cursor + Grok Bot

- Cursor's agent builds modules from the plan Page; conventions live in `.cursor/rules/astro-conventions.mdc`.
- Prompt history: `docs/prompt-log.md`.
- Planning and team coordination: Grok Bot (plan Page + check-ins).
- **Grok Voice** announcer and spoken judge Q&A (required for Make it Legendary).

## Phase 1 scope

Build only what the Phase 1 plan Page specifies until `scripts/mvp_gate.sh` prints PASS. Phase 2 sponsor integrations are out of scope until then.

## Quick start

```bash
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn backend.app:app --reload
npm --prefix frontend install
npm --prefix frontend run dev
```

Offline demo defaults (`USE_CACHED_STREAM=True`): replay `data/cache/`, no network on the trigger path. Keys may stay empty. Label every simulated number (`simulated=true` in JSON; Simulated badge in the UI).

## Community alerts (Phase 1)

Anyone with a telescope can subscribe for ranked progenitor coordinates as soon as BREAKOUT localizes a burst:

```bash
curl -X POST http://127.0.0.1:8000/subscribe \
  -H 'Content-Type: application/json' \
  -d '{"webhook_url":"https://your.site/hook","label":"campus-0.3m"}'
curl http://127.0.0.1:8000/alerts/latest
```

Default `NOTIFY_DRY_RUN=True` logs deliveries; set `NOTIFY_DRY_RUN=False` to POST live webhook JSON. Packages mark `simulated` honestly and only include ADS bibcodes already on each candidate.

## Layout

See the plan Page **Repo layout** section. Backend is FastAPI (`backend/`); frontend is Vite + TypeScript + Three.js (`frontend/`).

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
