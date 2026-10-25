# Project Supernova — frontend-v2 (parallel copy)

Optional parallel mission UI on port **5174**. The **primary** product entry is
now [`frontend/`](../frontend/) on **5173** (same product IA + Supernova design
language).

Setup details: [`docs/developers.md`](../docs/developers.md).

## Run

```bash
USE_CACHED_STREAM=True VOICE_MODE=off python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
npm --prefix frontend-v2 install
npm --prefix frontend-v2 run dev
```

Open http://127.0.0.1:5174 — prefer http://127.0.0.1:5173 for demos.
