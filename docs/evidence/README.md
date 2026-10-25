# Demo evidence captures

Screenshots and clips for Devpost / demo-day tab (Barron owns capture):

## MVP gate

- [x] Cursor rules file (`.cursor/rules/astro-conventions.mdc`) in the repo
- [ ] Commit timeline / graph spanning the 20 hours (Barron capture)
- [x] `docs/prompt-log.md` filled for each module
- [ ] Grok Bot plan Page + team check-ins (Barron)
- [ ] Betelgeuse run with announcer (`VOICE_MODE=live`) and Simulated badges (need `XAI_API_KEY` for live TTS; cached + mocked live covered in gate)
- [x] IceCube-170922A replay ending on TXS 0506+056 (`test_scenario_icecube`)
- [x] IceCube historical alert catalog pointing/fuse (`test_icecube_catalog`)
- [x] IceCube-230416A GCN schema example (`test_scenario_icecube_230416a`)
- [x] IceCube-191001A GCN 25913 archive (`test_scenario_icecube_191001a`)
- [x] Action tab: LCOGT dry-run JSON, ToO drafts, GCN Circular draft (`test_actions`)
- [x] Community subscribe + `/alerts/latest` ranked-candidate feed (`test_notify`)
- [x] `scripts/mvp_gate.sh` printing PASS

## Post-MVP demos

Capture on **frontend-v2 :5174** unless noted. Label every simulated number.

- [ ] Full-sky SVG Mollweide on load (catalog field stars + dashed galactic plane; no raster `<img>` in sky panel)
- [ ] Scenario A: smooth red 90% oval → CSS zoom of the same SVG → hover `* alf Ori` (posterior / p_sky)
- [ ] Evidence panel: select a ranked star; offline reasoning appears without flashing “no offline reasoning” (`ensure_raw_for_star`)
- [ ] Ranked list shows Distance / Conf / Life; sky hover shows life window + composition (inventory / v1.1)
- [ ] `python -m backend.progenitors status` + `GET /api/progenitors/inventory` smoke
- [ ] Community panel: subscribe → Scenario A → `/alerts/latest` package with `simulated=true`
- [ ] Actions drafts visible after candidates (LCOGT JSON dry-run, ToO Markdown, GCN **DRAFT**)
- [ ] Voice captions with Simulated note (`VOICE_MODE=cached` offline, or `live` with key)
- [ ] Scenario B Real-data path: IceCube-170922A → TXS 0506+056

Do not invent evidence. Clarify in captions: field stars = curated progenitors; dashed line = galactic plane.
