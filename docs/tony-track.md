# Tony — Phase 1 schedule + checklist

H0 = Sat 24 Oct 2026, **2:46 PM PDT**. MVP gate target ≈ H11 = Sun 1:46 AM PDT.

## 20-hour block tracker (Tony)

| Block | Window (PDT) | Focus | Status |
| --- | --- | --- | --- |
| H2–H4 | Sat 4:46–6:46 PM | candidates catalog + filter | Done (separate PR) |
| H4–H6 | Sat 6:46–8:46 PM | **literature/build_index.py** (this Page) | **Done this session** |
| **Next** | after merge | Ranking consume index; dashboard Simulated badges | Queued |

## Implementation checklist (this Page)

| Item | Status |
| --- | --- |
| `build_index.py` ADS + arXiv + Grok, Literature validate, drop unknown bibcodes | **Done** |
| Resume-safe + rate-limited; raw reasoning in `data/index/raw/` | **Done** |
| Tests with recorded responses | **Done** |
| Index built for every curated star (`* alf Ori`) | **Done** (replay; re-run live with keys) |

## Grok Bot / Cursor log

| When (PDT) | Tool | Used for |
| --- | --- | --- |
| Sat 24 Oct ~5:05 PM | Cursor agent | Offline literature index implementation + fixtures + curated build |

**Note:** Curated raw/`index.parquet` was produced with `--replay-dir` (recorded responses) because `ADS_API_TOKEN` / `XAI_API_KEY` were not in this environment. Live rebuild:

```bash
# .env must contain ADS_API_TOKEN and XAI_API_KEY
USE_CACHED_STREAM=False python -m backend.literature.build_index --curated-only --force
```
