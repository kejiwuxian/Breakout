# Community subscribers (Phase 1 MVP)

**In Phase 1 scope today:** scientists and astronomy enthusiasts subscribe to
BREAKOUT ranked-candidate alerts and point their own instruments at potential
optical counterparts before large facilities respond. This is community
follow-up for potential supernovae — not an official GCN notice and not a
confirmed detection.

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

**UI:** frontend-v2 (`:5174`) **Community push** rail and classic (`:5173`)
**Community alerts** panel. How-to: [`docs/community-subscribe.md`](../../docs/community-subscribe.md).
