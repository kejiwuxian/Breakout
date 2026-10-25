# Tony — Phase 1 schedule + checklist

H0 = Sat 24 Oct 2026, **2:46 PM PDT**. MVP gate target ≈ H11 = Sun 1:46 AM PDT.
Ignore Phase 2 until `scripts/mvp_gate.sh` prints PASS.

## 20-hour block tracker (Tony)

| Block | Window (PDT) | Focus | Status |
| --- | --- | --- | --- |
| H0–H2 | Sat 2:46–4:46 PM | Orient on plan Page; contract freeze landed (Light) | Done |
| H2–H4 | Sat 4:46–6:46 PM | candidates/catalog.py + filter.py | **Done** |
| H4–H6 | Sat 6:46–8:46 PM | literature/build_index.py | **Done** |
| H4–H6 / H7 | Sat ~5:14 PM onward | rerank + breakout_window + extinction | **Done** |
| H6–H8 | Sat 8:46–10:46 PM | Dashboard: skymap + candidate list + Simulated badges | **Done** |
| H8–H10 | Sat 10:46 PM–12:46 AM | Grok Voice frontend + judge Q&A wiring | **Done** |
| H10–H11 | Sun 12:46–1:46 AM | MVP gate rehearsal; fix FAIL items only | **Done** (`mvp_gate.sh` PASS) |
| H11+ | after gate PASS | Phase 2 Page + post-MVP product (skymap, inventory, notify UI, idle default) | **Done** — see `docs/post-mvp.md` |

## Implementation checklist

| Item | Status |
| --- | --- |
| `backend/candidates/catalog.py` — curated → parquet; SIMBAD/VizieR offline | **Done** |
| `backend/candidates/filter.py` — `candidates_in_region` + `p_sky` | **Done** |
| `build_index.py` ADS + arXiv + Grok; drop unknown bibcodes | **Done** |
| Index for curated stars (`* alf Ori`) | **Done** (replay; live with keys) |
| `breakout_window` / `extinction` / `rerank` config weights | **Done** |
| Dashboard Simulated badges + skymap/candidates UI | **Done** (H8) |
| Voice frontend / judge Q&A | **Done** (announcer panel + PTT judge Q&A) |

## Grok Bot / Cursor usage log

See `docs/prompt-log.md`.

| When (PDT) | Used for |
| --- | --- |
| Sat 24 Oct ~4:53–5:15 PM | catalog + filter |
| Sat 24 Oct ~5:05 PM | literature build_index |
| Sat 24 Oct ~5:14 PM | ranking physics (H7) |
| Sat 24 Oct ~5:29–5:45 PM | dashboard panels + Simulated/Real badges (H8) |

**Note:** Literature index from `--replay-dir` when keys absent. Live rebuild:

```bash
USE_CACHED_STREAM=False python -m backend.literature.build_index --curated-only --force
```

Rules: real data real; nulls stay null; `simulated=true` for simulated skymaps; no invented bibcodes.

**Known follow-up (Bugbot):** Scenario B IceCube HE_NEUTRINO may need fuse pointing from IceCube DetectorHit RA/Dec (single-detector path) — tracked for later, not blocking H8 dashboard merge.
