# Community event push (two-token email subscribe)

Phase 1 lets anyone with a telescope opt in for ranked progenitor coordinates
when BREAKOUT localizes an `SN_BURST` / `HE_NEUTRINO` candidate set. This is
**community follow-up**, not an official GCN notice and not a confirmed
supernova detection service.

**No webhooks.** Delivery is email-only to **confirmed** subscribers after a
two-token auth flow. That cuts abuse and wasted fan-out work from unverified
endpoints.

## Two-token flow

1. **Request** — `POST /subscribe/request` with `email` (+ optional `label`).
   Server creates a **pending** subscriber, stores **hashed** short-lived
   `request_token` + `confirm_token` (TTL ≈ 1 hour), and does **not** send
   alert pushes yet. Response is `{ pending: true, request_id, … }` without
   echoing secrets at the top level.
2. **Confirm** — `POST /subscribe/confirm` with both tokens. On success the
   subscriber becomes **active** and receives a durable `access_token` (also
   hashed at rest). Tokens cannot be reused; expired/bad tokens are rejected.
3. **Dispatch** — only **active** subscribers get email on the next ranked
   package. Pending rows never receive alerts. There is no webhook path.

### Dry-run / no SMTP

With default `NOTIFY_DRY_RUN=True`, or when `SMTP_HOST` is unset, the request
response includes a `dry_run` object labeled **Simulated/dry-run** with both
tokens so local demos can confirm without inventing production email delivery.
Live mail is only attempted when dry-run is off **and** SMTP is configured.

Abuse controls (Phase 1): in-memory rate limit by email + IP, pending expiry,
hashed tokens at rest, active-only public listing with masked emails.

## Subscribe from the UI

| UI | Port | Where |
| --- | --- | --- |
| **frontend-v2** (primary) | `5174` | Rail block **Community push** |
| Classic `frontend/` | `5173` | **Community alerts** panel |

1. Start the API (`uvicorn backend.app:app`, typically `:8000`).
2. Open frontend-v2 at http://127.0.0.1:5174 (Vite proxies `/subscribe` and `/alerts`).
3. **Step 1:** enter email (+ optional label) → **Request**.
4. In dry-run, copy the Simulated/dry-run tokens shown in the panel into **Step 2** → **Confirm**.
5. Active subscribers appear in the list (masked email). Browse packages at
   [`GET /alerts/latest`](http://127.0.0.1:8000/alerts/latest).

## What gets pushed

Feed packages (`breakout.community_alert.v1`) include:

- Alert metadata (`alert_id`, `kind`, `source`, `t0_utc`, …)
- Skymap peak RA/Dec and credible region size
- Ranked candidates with **ICRS** `ra_deg` / `dec_deg`, posterior, class window
- `simulated=true` when any field is simulated
- ADS bibcodes **only** when already present on the candidate (never invented)

Registry and append-only feed live under `data/subscribers/` (see
[`data/subscribers/README.md`](../data/subscribers/README.md)).

## Dry-run vs live

| Setting | Behavior |
| --- | --- |
| `NOTIFY_DRY_RUN=True` (default) | Request returns Simulated/dry-run tokens in JSON; alert emails logged only |
| `NOTIFY_DRY_RUN=False` + `SMTP_HOST` set | Confirm tokens would be emailed; alert email path enabled (Phase 1 SMTP still minimal) |
| `NOTIFY_DRY_RUN=False` without SMTP | Tokens still returned in API for demos; no invented outbound mail |

Health reports the flag: `GET /health` → `notify_dry_run`, `n_subscribers` (active only).

## API

```bash
# Step 1 — request (dry-run returns tokens under dry_run)
curl -X POST http://127.0.0.1:8000/subscribe/request \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@observatory.edu","label":"campus-0.3m"}'

# Step 2 — confirm with both tokens from dry_run (or email)
curl -X POST http://127.0.0.1:8000/subscribe/confirm \
  -H 'Content-Type: application/json' \
  -d '{"request_token":"…","confirm_token":"…"}'

curl http://127.0.0.1:8000/alerts/latest
# Optional: ?token=<access_token> or Authorization: Bearer <access_token>
```

| Method | Path | Role |
| --- | --- | --- |
| `POST` | `/subscribe/request` | Pending subscribe (email + optional label) |
| `POST` | `/subscribe/confirm` | Activate with both tokens; returns `access_token` |
| `POST` | `/subscribe` | Alias of `/subscribe/request` (email only; no webhook) |
| `GET` | `/subscribe` | Active subscriber metadata (masked email) |
| `DELETE` | `/subscribe/{id}` | Unsubscribe |
| `GET` | `/alerts/latest` | Recent ranked-candidate packages |

Implementation: `backend/notify/` (`subscribers.py`, `dispatch.py`, `payload.py`).
