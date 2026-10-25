# Tony — Phase 1 schedule + checklist

H0 = Sat 24 Oct 2026, **2:46 PM PDT**. MVP gate target ≈ H11 = Sun 1:46 AM PDT.
Ignore Phase 2 **sponsor** integrations until `scripts/mvp_gate.sh` prints PASS (community notify is Phase 1).

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
| H11+ | after gate PASS | Post-MVP demo polish (not sponsor Phase 2) | **In progress** — see below |

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

## Post-MVP tracks (H11+)

| Track | Status |
| --- | --- |
| Community notify (`/subscribe`, `/alerts/latest`) | **Done** (Phase 1 claim) |
| Actions: LCOGT dry-run / ToO / GCN draft | **Done** |
| Grok Voice announcer + judge tools | **Done** |
| frontend-v2 redesigned mission UI (:5174) | **Done** |
| SVG skymap: full sky, oval, zoom, hover, galactic plane, curated field stars | **Done** |
| Evidence `ensure_raw_for_star` (no flash) | **Done** |
| Progenitors inventory + `rank_with_grok` + CONF/life/composition UI | **Done** |
| SNEWS DiffPointing + live public channels | **Done** (Light) |
| IceCube historical scenarios / catalog | **Done** (Light) |

Index: [`docs/post-mvp.md`](post-mvp.md).

## Grok Bot / Cursor usage log

See `docs/prompt-log.md`.

| When (PDT) | Used for |
| --- | --- |
| Sat 24 Oct ~4:53–5:15 PM | catalog + filter |
| Sat 24 Oct ~5:05 PM | literature build_index |
| Sat 24 Oct ~5:14 PM | ranking physics (H7) |
| Sat 24 Oct ~5:29–5:45 PM | dashboard panels + Simulated/Real badges (H8) |
| Sat–Sun post-gate | frontend-v2, SVG skymap, inventory UI (see prompt-log) |

**Note:** Literature index from `--replay-dir` when keys absent. Live rebuild:

```bash
USE_CACHED_STREAM=False python -m backend.literature.build_index --curated-only --force
```

Rules: real data real; nulls stay null; `simulated=true` for simulated skymaps; no invented bibcodes.

**Resolved follow-up:** Scenario B IceCube HE_NEUTRINO fuse uses published IceCube pointing from archive notices (single-detector path); DiffPointing applies to multi-detector SNEWS timing, not HE_NEUTRINO alone.
