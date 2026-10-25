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
| Sat 24 Oct 2026, ~7:20–7:40 PM PT | Light + Cursor agent | Actions layer (LCOGT dry-run, HST/JWST ToO, GCN draft) + Grok Voice backend (announcer/session/tools) | PRs #12/#13 |
| Sat 24 Oct 2026, ~7:40 PM PT | Light + Cursor agent | Offline test + preflight.sh + full mvp_gate.sh; cached voice clips; `*` alert_id voice URL fix | commit `offline: preflight and MVP gate` (PR #14) |
| Sat 24 Oct 2026, ~7:40 PM PT | Tony + Cursor agent | Grok Voice frontend panel: captions, mute, push-to-talk judge Q&A over realtime tools | PR #15 |
| Sat 24 Oct 2026, ~7:41–8:00 PM PT | Light + Cursor agent | Review plan Page; merge standing PRs onto main for code freeze; Scenario B GCN archive copies; gate PASS | mainline MVP freeze |
| Sat 24 Oct 2026, ~8:16 PM PT | Light + Cursor agent | Review SNEWS2/SNEWS_Coincidence_System for direction finding; adopt snewpdag DiffPointing joint-χ² (Coincidence System has no skymap) into localize/fuse | `backend/localize/snews_diffpointing.py` |
| Sat 24 Oct 2026, ~8:35 PM PT | Light + Cursor agent | Confirm real-data validation still PASS after DiffPointing; add IceCube historical alert catalog + Scenario C (GCN IceCube-230416A example); document SN1987A clock limits | `data/cache/icecube_alert_catalog/`, `scenario_c_icecube_230416a/` |
| Sat 24 Oct 2026, ~8:40 PM PT | Light + Cursor agent | Add Scenario D IceCube-191001A from GCN Circular 25913 + AMON archive; re-run real-data suite | `scenario_d_icecube_191001a/`, tests green |
| Sat 24 Oct 2026, ~8:50 PM PT | Light + Cursor agent | Subscribe all public realtime channels (SNEWS2 GCN + classic SNEWS + IceCube + pre-SN + optional Hopskotch); self-localize via DiffPointing; epoch PM only when catalog has published values (no ranking impact at nside=64) | `live_channels`, `snews_classic`, `epoch_position` |
| Sat 24 Oct 2026, ~10:10 PM PT | Light + Cursor agent | Phase 1 community notify: webhook/email subscribe + ranked-candidate alert feed so enthusiasts can point instruments today | `backend/notify/`, `/subscribe`, `/alerts/latest`, UI panel |
| Sat 24 Oct 2026, ~10:15 PM PT | Light + Cursor agent | Lock community notify into Phase 1 MVP claim language + mvp_gate (`test_notify`) so we can say BREAKOUT already helps catch potential SNe today | README Phase 1 scope, `scripts/mvp_gate.sh`, judge Q&A 18b |
| Sat 24 Oct 2026, ~10:55 PM PT | Light + Cursor agent | Interactive skymap: latest fused region.json + focus PNG; Aladin DSS zoom + red 90% outline; hover ranked stars for posterior/p_sky | `backend/localize/region.py`, `/api/skymap/*/region`, frontend-v2 sky panel |
| Sun 25 Oct 2026, ~12:10 AM PT | Light + Cursor agent | Full-sky default + smooth zoom-in; localization area as smooth oval (covariance ellipse), not jagged HEALPix ring | `credible_region_ellipse`, frontend-v2 sky zoom animation |
| Sun 25 Oct 2026, ~3:10 AM PT | Light + Cursor agent | Stop evidence panel flashing “no offline reasoning”; materialize raw JSON from ADS/arXiv fixtures or index.parquet | `ensure_raw_for_star`, candidates cache + tick-only countdown |
| Sun 25 Oct 2026, ~3:25 AM PT | Light + Cursor agent | Pure SVG Mollweide skymap (public catalog + galactic plane + HEALPix cells); zoom without raster swap | `render=svg_v1`, `/api/sky/base`, frontend-v2 svgMap |
| Sun 25 Oct 2026, ~3:40 AM PT | Light + Cursor agent | Grok progenitor inventory + publication monitor; AOI filter + offline/live rank with confidence; sorted list + sky hover details | `backend/progenitors/`, CandidateScore v1.1, frontend-v2 candidates/sky |
| Sun 25 Oct 2026, ~3:55 AM PT | Light + Cursor agent | SVG mouse wheel zoom / drag pan + AOI zoom on event | `frontend-v2` sky viewBox camera |
| Sun 25 Oct 2026, ~4:00 AM PT | Vincent + Cursor agent | Phase 2 after MVP gate PASS: P2.0 flags + `test_flags_off`; P2.3 Apify actor (flag default False, offline only) | `actors/breakout-star-literature/`, `APIFY_ENABLED` |
| Sun 25 Oct 2026, ~4:05 AM PT | Light + Cursor agent | Community push UI + two-token email subscribe (no webhook) | `backend/notify/`, frontend-v2 subscribe rail |
| Sun 25 Oct 2026, ~4:15 AM PT | Light + Cursor agent | Idle live-waiting default; manual scenario only | `BREAKOUT_AUTOSTART`, `scenario=live_waiting` |
| Sun 25 Oct 2026, ~4:30 AM PT | Light + Cursor agent | Review/merge post-MVP PR stack onto main; refresh docs | `docs/post-mvp.md`, README |

Notes:

- Plan Page: https://breakout-revised-hackathon-plan-and-7czo.pages.grok.bot/
- Phase 2 Page: https://breakout-phase-2-sponsor-integrations-omyo.pages.grok.bot/
- Phase 2 sponsor integrations behind flags (default off). Community subscribe is Phase 1.
- Post-MVP feature index: `docs/post-mvp.md`.
- Never invent numbers or citations; simulated values use `simulated=true`.
