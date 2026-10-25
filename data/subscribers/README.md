# Community subscribers (Phase 1 MVP)

**In Phase 1 scope today:** scientists and astronomy enthusiasts confirm an
email via a **two-token** flow, then receive BREAKOUT ranked-candidate alerts
so they can point instruments at potential optical counterparts before large
facilities respond. This is community follow-up for potential supernovae — not
an official GCN notice and not a confirmed detection.

**No webhooks.** Only confirmed (active) subscribers get email dispatch.

| Path | Role |
| --- | --- |
| `POST /subscribe/request` | Pending: email + optional label; hashed request/confirm tokens |
| `POST /subscribe/confirm` | Activate with both tokens; issues durable `access_token` |
| `POST /subscribe` | Alias of `/subscribe/request` |
| `GET /subscribe` | List **active** subscriber metadata (masked email) |
| `DELETE /subscribe/{id}` | Unsubscribe |
| `GET /alerts/latest` | Recent alert packages (optional `token` / Bearer auth) |
| `registry.json` | Local registry (gitignored; created at runtime) |
| `alert_feed.jsonl` | Append-only feed of dispatched packages |

Pending rows expire (~1 hour). Tokens are **hashed at rest**. Rate limits apply
per email and IP. `NOTIFY_DRY_RUN=True` (default) returns Simulated/dry-run
tokens in the request JSON and logs alert emails without SMTP.

Every package sets `simulated=true` when any field is simulated. Evidence
bibcodes are copied only from CandidateScore — never invented.

**UI:** frontend-v2 (`:5174`) **Community push** rail and classic (`:5173`)
**Community alerts** panel. How-to: [`docs/community-subscribe.md`](../../docs/community-subscribe.md).
