# Community event push (subscribe UI)

Phase 1 lets anyone with a telescope (or a webhook script) opt in for ranked
progenitor coordinates when BREAKOUT localizes an `SN_BURST` / `HE_NEUTRINO`
candidate set. This is **community follow-up**, not an official GCN notice and
not a confirmed supernova detection service.

## Subscribe from the UI

| UI | Port | Where |
| --- | --- | --- |
| **frontend-v2** (primary) | `5174` | Rail block **Community push** |
| Classic `frontend/` | `5173` | **Community alerts** panel |

1. Start the API (`uvicorn backend.app:app`, typically `:8000`).
2. Open frontend-v2 at http://127.0.0.1:5174 (Vite proxies `/subscribe` and `/alerts`).
3. Enter a webhook URL and/or email, optional label, then **Subscribe**.
4. Success shows in the status line. With default `NOTIFY_DRY_RUN=True`,
   deliveries are **logged only** (not POSTed / emailed).
5. Browse recent packages at [`GET /alerts/latest`](http://127.0.0.1:8000/alerts/latest)
   (link also appears in the panel).

## What gets pushed

Webhook body / feed packages (`breakout.community_alert.v1`) include:

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
| `NOTIFY_DRY_RUN=True` (default) | Webhook/email deliveries logged; no outbound POST/SMTP |
| `NOTIFY_DRY_RUN=False` | Live webhook JSON POST; email only if SMTP is configured |

Health reports the flag: `GET /health` → `notify_dry_run`, `n_subscribers`.

## API (unchanged)

```bash
curl -X POST http://127.0.0.1:8000/subscribe \
  -H 'Content-Type: application/json' \
  -d '{"webhook_url":"https://your.site/hook","label":"campus-0.3m"}'
curl http://127.0.0.1:8000/alerts/latest
```

| Method | Path | Role |
| --- | --- | --- |
| `POST` | `/subscribe` | Register `webhook_url` and/or `email` |
| `GET` | `/subscribe` | Public subscriber metadata (hosts only) |
| `DELETE` | `/subscribe/{id}` | Unsubscribe |
| `GET` | `/alerts/latest` | Recent ranked-candidate packages |

Implementation: `backend/notify/` (`subscribers.py`, `dispatch.py`, `payload.py`).
