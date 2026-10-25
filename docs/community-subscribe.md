# Subscribe to events (open access + refresh over WebSocket)

Anyone can subscribe for ranked progenitor coordinates when **Project Supernova**
localizes an `SN_BURST` / `HE_NEUTRINO` candidate set. **No account and no prior
credentials** — `POST /subscribe` mints tokens for any caller (rate-limited).

This is **community follow-up**, not an official GCN notice and not a confirmed
supernova detection service.

**Two-token auth** = **access token** + **refresh token**. Live delivery is
over **WebSocket** (`/ws/subscribe`).

Public demo origin: **`https://supernova.lylinks.com`**. Local uvicorn stays on
`http://127.0.0.1:8000`. Set `BASE_URL` accordingly (or `BREAKOUT_PUBLIC_BASE_URL`).

## 1. Issue tokens

```bash
BASE_URL="${BREAKOUT_PUBLIC_BASE_URL:-https://supernova.lylinks.com}"
# Local dry-run: BASE_URL=http://127.0.0.1:8000
curl -X POST "$BASE_URL/subscribe" \
  -H 'Content-Type: application/json' \
  -d '{}'
# optional label: {"label":"campus-0.3m"}
```

Response includes:

| Field | Meaning |
| --- | --- |
| `access_token` | Short-lived (~5 min). Required to open `/ws/subscribe`. |
| `refresh_token` | Longer-lived (~7 days). Exchange for a new access token. |
| `access_expires_utc` | When the current access token dies. |
| `ws` | `/ws/subscribe` |

Tokens are **hashed at rest**. Empty body is enough — email is optional and not required to listen.

## 2. Refresh access

```bash
curl -X POST "$BASE_URL/subscribe/refresh" \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token":"…"}'
```

Returns a new `access_token` and a **rotated** `refresh_token`. Old refresh
tokens cannot be reused.

## 3. WebSocket

```text
# Production (Cloudflare tunnel)
wss://supernova.lylinks.com/ws/subscribe?access_token=<access_token>
# Local
ws://127.0.0.1:8000/ws/subscribe?access_token=<access_token>
```

Or connect without a query string and send as the first frame:

```json
{"type":"auth","access_token":"<access_token>"}
```

Server hello:

```json
{"type":"subscribe_hello","subscriber_id":"…","access_expires_utc":"…","expires_in_sec":…}
```

**Extend** a live session after refresh — send the new access token on the same wire:

```json
{"type":"access_token","access_token":"<new_access_token>"}
```

Server replies `access_extended` and reschedules the close timer.

**Auto-close:** if access expires without a successful extend, the socket closes
with code **4001** (`access_token_expired`).

**Events:** ranked packages arrive as:

```json
{"type":"community_alert","payload":{…},"simulated":true}
```

## Subscribe from the UI

| UI | Port | Where |
| --- | --- | --- |
| **`frontend/`** (primary) | `5173` | Rail **Subscribe to events** |
| Optional `frontend-v2/` | `5174` | Parallel copy of the same rail |

1. Start the API (`uvicorn backend.app:app`, typically `:8000`) — or
   `bash scripts/run_public.sh` for the tunnel at https://supernova.lylinks.com.
2. Open the primary UI at http://127.0.0.1:5173 (Vite proxies `/subscribe`,
   `/alerts`, `/ws`), or the public host when tunneling (API serves `frontend/dist`).
3. Optional label → **Get tokens & connect**. The panel documents the three
   endpoints inline, opens `/ws/subscribe`, and auto-refreshes before expiry.
4. Browse `GET /alerts/latest` on the same origin (local `:8000` or
   https://supernova.lylinks.com/alerts/latest).
5. Exercise a push with a manual Replay scenario (`simulated=true` when applicable).

## What gets pushed

Feed packages (`breakout.community_alert.v1`) include alert metadata, skymap
peak RA/Dec, ranked ICRS candidates, `simulated=true` when applicable, and ADS
bibcodes **only** when already on the candidate.

## API summary

| Method | Path | Role |
| --- | --- | --- |
| `POST` | `/subscribe` | Issue access + refresh (no prior credentials) |
| `POST` | `/subscribe/refresh` | New access token (+ rotated refresh) |
| `WS` | `/ws/subscribe` | Live event push (access-gated; auto-close on expiry) |
| `GET` | `/subscribe` | Active subscriber metadata (masked) |
| `DELETE` | `/subscribe/{id}` | Unsubscribe |
| `GET` | `/alerts/latest` | Recent packages (optional Bearer / `?token=`) |

Abuse controls: in-memory rate limit by IP (and email if provided), hashed
tokens, refresh rotation. Implementation: `backend/notify/`.
