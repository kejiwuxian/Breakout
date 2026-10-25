# Cursor / Grok Bot prompt log

Evidence for SpaceXAI "Make it Legendary" and MLH A-Team: agent-built modules,
planning collaboration, and steady commits. Log each prompt that builds a module.

| When (PT) | Who | Prompt / task | Outcome |
| --- | --- | --- | --- |
| Sat 24 Oct 2026, ~4:16 PM PT | Light + Cursor agent | Scaffold Phase 1 repo from plan Page: FastAPI + Vite/TS/Three.js layout, typed stubs, schemas doc, `.env.example`, health test; three commits (scaffold, rules, CI) | This scaffold |
| Sat 24 Oct 2026, ~4:25 PM PT | Light + Cursor agent | Implement `ingest/snewpy_sim.py` + `ingest/cache.py`: detector WGS84 table, snewpy event rates, geometric −r·û/c arrivals, CLI, async cache replay with speed factor; tests for baseline/c, along-baseline max delay, replay order/timing, schema; one commit per module | Modules + tests green; Scenario A cache written with `simulated=true` |
| Sat 24 Oct 2026, ~4:30 PM PT | Light + Cursor agent | Implement `ingest/presn.py`, `snews.py`, `gcn_kafka.py` with gcn-kafka; public/synthetic fixtures; no network when USE_CACHED_STREAM=True; one commit per module | pytest green |
| Sat 24 Oct 2026, ~4:34 PM PT | Light + Cursor agent | Implement `localize/triangulate.py`, `pointing.py`, `fuse.py` (healpy NESTED nside=64, FITS+Mollweide PNG); tests for sum=1, true pos in 90%, pointing shrinks area; one commit per module | pytest green |
| Sat 24 Oct 2026, ~4:38 PM PT | Light + Cursor agent | Freeze CandidateScore v1 contract: Evidence/Literature/Breakout models, export JSON Schema to docs/schemas/, fixture wrappers with simulated=true, test_contract.py | commit `contract: freeze CandidateScore v1` |
| Sat 24 Oct 2026, ~4:43 PM PT | Light + Cursor agent | Wire e2e core loop in app.py (cache replay → fuse → filter → rerank → WS events); POST /scenario/start; test_e2e with network blocked | commit `e2e: core loop` |
| Sat 24 Oct 2026, ~4:53–5:20 PM PT | Tony + Cursor agent | Implement `candidates/catalog.py` (curated → parquet; SIMBAD otypes + VizieR III/215 WR + J/AJ/158/20 RSG offline) and `filter.candidates_in_region` with `p_sky`; USE_CACHED_STREAM reads parquet only; one commit per module; Tony block/checklist track | commits catalog + filter; `docs/tony-track.md` |
| Sat 24 Oct 2026, ~4:55 PM PT | Light + Cursor agent | Betelgeuse Scenario A: curated Joyce 0.168 kpc, simulate_presn + SN_BURST from curated, index.parquet ADS evidence, README real vs simulated, test_scenario_betelgeuse | commit `scenario: Betelgeuse` |
| Sat 24 Oct 2026, ~5:05–5:20 PM PT | Tony + Cursor agent | Implement OFFLINE `literature/build_index.py`: ADS + arXiv retrieval, Grok Literature JSON, drop unknown bibcodes, resume/rate-limit, raw reasoning under `data/index/raw/`, index.parquet for curated stars; tests with recorded responses; one commit per step | commits implement → tests → curated index |
| Sat 24 Oct 2026, ~5:14 PM PT | Tony + Cursor agent | Implement `breakout_window`, `extinction`, `rerank` with config weights; normalized posteriors; tests for ordering / class windows / IR flag | commits physics + rerank; H7 ranking path done |
| Sat 24 Oct 2026, ~5:20 PM PT | Light + Cursor agent | Integrate Tony H7 PRs (#2 catalog/filter, #3 build_index, #4 rerank/physics) onto Betelgeuse scenario branch; fix catalog distance assertions for Joyce 0.168 kpc; full pytest green | commit `integrate: Tony H7` |
| Sat 24 Oct 2026, ~5:29–5:45 PM PT | Tony + Cursor agent | Dashboard panels (sky map, candidates+ADS, scenario buttons, Simulated/Real badges); WS `/ws/events`; copy in `strings.json`; one commit per panel | frontend dashboard (H8) |
| Sat 24 Oct 2026, ~5:38 PM PT | Light + Cursor agent | Review and merge all open PRs after Tony H8; integrate dashboard + ranking contract onto mainline | merge stack to main |

Notes:

- Plan Page: https://breakout-revised-hackathon-plan-and-7czo.pages.grok.bot/
- Phase 2 (sponsor integrations) ignored until `scripts/mvp_gate.sh` prints PASS.
- Never invent numbers or citations; simulated values use `simulated=true`.
