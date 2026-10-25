# Tony — Phase 1 schedule + checklist

H0 = Sat 24 Oct 2026, **2:46 PM PDT**. MVP gate target ≈ H11 = Sun 1:46 AM PDT.
Ignore Phase 2 until `scripts/mvp_gate.sh` prints PASS.

## 20-hour block tracker (Tony)

| Block | Window (PDT) | Focus | Status |
| --- | --- | --- | --- |
| H0–H2 | Sat 2:46–4:46 PM | Orient on plan Page; contract freeze landed (Light) | Done (scaffold + contract exist) |
| H2–H4 | Sat 4:46–6:46 PM | **candidates/catalog.py + filter.py** (this Page) | **In progress → done this session** |
| H4–H6 | Sat 6:46–8:46 PM | Ranking / literature consume CandidateScore; clocks + extinction hooks | Next |
| H6–H8 | Sat 8:46–10:46 PM | Dashboard: skymap + candidate list + Simulated badges | Queued |
| H8–H10 | Sat 10:46 PM–12:46 AM | Grok Voice frontend + judge Q&A wiring | Queued |
| H10–H11 | Sun 12:46–1:46 AM | MVP gate rehearsal; fix FAIL items only | Queued |
| H11+ | after gate PASS | Phase 2 Page only | Blocked on gate |

### What’s next (after this block)

1. Confirm `pytest` stays green on mainline after catalog/filter merge.
2. Start ranking path: `literature/rerank.py` already stubs posterior; wire Tony’s checklist item for class weights / clocks / dust using real null-safe fields from `star_table`.
3. Dashboard: render `p_sky`, `simulated` badge, never invent numbers.

## Implementation checklist (Tony items on this Page)

| Item | Owner | Status |
| --- | --- | --- |
| `backend/candidates/catalog.py` — curated → parquet; SIMBAD otypes + VizieR WR/RSG offline | Tony + Cursor | **Done** (`candidates: catalog` commit) |
| `backend/candidates/filter.py` — `candidates_in_region(skymap, star_table, level=0.9)` + `p_sky` | Tony + Cursor | **Done** (`candidates: filter` commit) |
| Tests: fixture map selects expected stars; USE_CACHED_STREAM reads parquet only | Tony + Cursor | **Done** (`tests/test_catalog.py`, `tests/test_filter.py`) |
| Ranking conforms to CandidateScore v1 | Tony | Pending (placeholder `test_contract_ranking.py`) |
| Dashboard Simulated badges + skymap/candidates UI | Tony | Pending |
| Voice frontend / judge Q&A | Tony | Pending |

## Grok Bot / Cursor usage log (Devpost evidence)

See also `docs/prompt-log.md`. This session:

| When (PDT) | Tool | What we used it for |
| --- | --- | --- |
| Sat 24 Oct 2026, ~4:53 PM | Grok Bot plan Page | Read Phase 1 scope; catalog/filter acceptance from Page |
| Sat 24 Oct 2026, ~4:55–5:15 PM | Cursor agent (this chat) | Implement `catalog.py` + `filter.py`, pytest, one commit per module, schedule/checklist tracking |

Rules followed: real data real; nulls stay null; `simulated=true` when the skymap is simulated; no invented bibcodes; network only in offline `build_star_table(--network)`.
