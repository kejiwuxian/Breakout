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
