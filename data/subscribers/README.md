# Community subscribers (Phase 1 MVP)

Scientists and astronomy enthusiasts can **subscribe** to BREAKOUT ranked-candidate
alerts and point their own instruments before large facilities respond.

| Path | Role |
| --- | --- |
| `POST /subscribe` | Register `webhook_url` and/or `email` |
| `GET /subscribe` | List subscriber metadata (hosts only) |
| `DELETE /subscribe/{id}` | Unsubscribe |
| `GET /alerts/latest` | Recent alert packages (ranked stars + ICRS coords) |
| `registry.json` | Local registry (gitignored; created at runtime) |
| `alert_feed.jsonl` | Append-only feed of dispatched packages |

`NOTIFY_DRY_RUN=True` (default) logs webhook deliveries without POSTing.
Set `NOTIFY_DRY_RUN=False` to POST live JSON to registered webhooks.

Every package sets `simulated=true` when any field is simulated. Evidence
bibcodes are copied only from CandidateScore — never invented.
