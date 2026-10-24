# Cursor / Grok Bot prompt log

Evidence for SpaceXAI "Make it Legendary" and MLH A-Team: agent-built modules,
planning collaboration, and steady commits. Log each prompt that builds a module.

| When (PT) | Who | Prompt / task | Outcome |
| --- | --- | --- | --- |
| Sat 24 Oct 2026, ~4:16 PM PT | Light + Cursor agent | Scaffold Phase 1 repo from plan Page: FastAPI + Vite/TS/Three.js layout, typed stubs, schemas doc, `.env.example`, health test; three commits (scaffold, rules, CI) | This scaffold |
| Sat 24 Oct 2026, ~4:25 PM PT | Light + Cursor agent | Implement `ingest/snewpy_sim.py` + `ingest/cache.py`: detector WGS84 table, snewpy event rates, geometric −r·û/c arrivals, CLI, async cache replay with speed factor; tests for baseline/c, along-baseline max delay, replay order/timing, schema; one commit per module | Modules + tests green; Scenario A cache written with `simulated=true` |

Notes:

- Plan Page: https://breakout-revised-hackathon-plan-and-7czo.pages.grok.bot/
- Phase 2 (sponsor integrations) ignored until `scripts/mvp_gate.sh` prints PASS.
- Never invent numbers or citations; simulated values use `simulated=true`.
