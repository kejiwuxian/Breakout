# Community event push (access + refresh over WebSocket)

Phase 1 lets anyone with a telescope opt in for ranked progenitor coordinates
when BREAKOUT localizes an `SN_BURST` / `HE_NEUTRINO` candidate set. This is
**community follow-up**, not an official GCN notice and not a confirmed
supernova detection service.

**Two-token auth** means **access token** + **refresh token** (not an email
confirm dance). Live delivery is over **WebSocket** (`/ws/subscribe`).

## Token + WebSocket flow

1. **Issue** — `POST /subscribe` with optional `email` / `label`.
   Server creates an **active** subscriber and returns:
   - `access_token` (short-lived, default ~5 minutes)
   - `refresh_token` (longer-lived, default ~7 days; rotated on use)
   Tokens are **hashed at rest**.
2. **Connect** — open `ws(s)://…/ws/subscribe?access_token=…`
   (or send `{ "type": "auth", "access_token": "…" }` as the first frame).
   Server replies with `subscribe_hello` including `access_expires_utc`.
3. **Extend** — before access expiry, `POST /subscribe/refresh` with
   `refresh_token`, then send the new access token on the **live** socket:
   `{ "type": "access_token", "access_token": "…" }`.
   Server replies `access_extended` and reschedules the close timer.
4. **Auto-close** — if the access token expires without a successful extend,
   the server closes the wire with code **4001** (`access_token_expired`).
5. **Dispatch** — ranked packages are pushed as `{ "type": "community_alert", "payload": … }`
   to connected sockets. Optional email mirror remains dry-run unless SMTP is configured.

Abuse controls: in-memory rate limit by email + IP, hashed tokens at rest,
masked emails on the public list, refresh rotation.

## Subscribe from the UI

| UI | Port | Where |
| --- | --- | --- |
| **frontend-v2** (primary) | `5174` | Rail block **Community push** |
| Classic `frontend/` | `5173` | **Community alerts** panel |

1. Start the API (`uvicorn backend.app:app`, typically `:8000`). Cold start is
   **idle / listening** — no auto Scenario A unless `BREAKOUT_AUTOSTART=1`.
2. Open frontend-v2 at http://127.0.0.1:5174 (Vite proxies `/subscribe`, `/alerts`, `/ws`).
3. Enter optional email/label → **Subscribe**.
4. The panel opens `/ws/subscribe` and auto-refreshes access before expiry.
5. Browse the JSON feed at [`GET /alerts/latest`](http://127.0.0.1:8000/alerts/latest).
6. To exercise a push locally, manually **Run** a Replay scenario.

## What gets pushed

Feed packages (`breakout.community_alert.v1`) include:

- Alert metadata (`alert_id`, `kind`, `source`, `t0_utc`, …)
- Skymap peak RA/Dec and credible region size
- Ranked candidates with **ICRS** `ra_deg` / `dec_deg`, posterior, class window
- `simulated=true` when any field is simulated
- ADS bibcodes **only** when already present on the candidate (never invented)

Registry and append-only feed live under `data/subscribers/` (see
[`data/subscribers/README.md`](../data/subscribers/README.md)).

## API

```bash
# Issue access + refresh
curl -X POST http://127.0.0.1:8000/subscribe \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@observatory.edu","label":"campus-0.3m"}'

# Refresh access (then send new access_token on the live WS)
curl -X POST http://127.0.0.1:8000/subscribe/refresh \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token":"…"}'

# WebSocket (websocat / wscat)
# wscat -c "ws://127.0.0.1:8000/ws/subscribe?access_token=…"

curl http://127.0.0.1:8000/alerts/latest
# Optional: ?token=<access_token> or Authorization: Bearer <access_token>
```

| Method | Path | Role |
| --- | --- | --- |
| `POST` | `/subscribe` | Issue access + refresh tokens |
| `POST` | `/subscribe/refresh` | New access token (+ rotated refresh) |
| `GET` | `/subscribe` | Active subscriber metadata (masked email) |
| `DELETE` | `/subscribe/{id}` | Unsubscribe |
| `WS` | `/ws/subscribe` | Live community alert push (access-gated) |
| `GET` | `/alerts/latest` | Recent ranked-candidate packages |

Implementation: `backend/notify/` (`subscribers.py`, `ws_hub.py`, `dispatch.py`, `payload.py`).
