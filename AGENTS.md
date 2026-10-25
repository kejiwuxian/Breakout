# Agent notes

## Cursor Cloud specific instructions

- **Local preview must always run the latest code under test.** After any code change, restart backend `:8000` and frontend-v2 `:5174` from the worktree/branch being changed. Do not leave stale `uvicorn`/`vite` processes pointing at an old worktree or branch. Kill stale listeners by PID only (never `pkill -f`).
- **Primary UI** is `frontend-v2` on `http://127.0.0.1:5174`.
- **API** is `uvicorn backend.app:app` on `http://127.0.0.1:8000` (typical env: `USE_CACHED_STREAM=True VOICE_MODE=off BREAKOUT_DISABLE_AUTOSTART=0`).
