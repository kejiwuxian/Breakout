# Community subscribers (Phase 1 MVP)

**In Phase 1 scope today:** scientists and astronomy enthusiasts issue
**access + refresh** tokens, then receive BREAKOUT ranked-candidate alerts on
**`/ws/subscribe`**. This is community follow-up for potential supernovae — not
an official GCN notice and not a confirmed detection.

| Path | Role |
| --- | --- |
| `POST /subscribe` | Issue access_token + refresh_token |
| `POST /subscribe/refresh` | Rotate tokens; push new access on live WS to extend |
| `WS /ws/subscribe` | Live push; auto-closes when access expires (code 4001) |
| `GET /subscribe` | List **active** subscriber metadata (masked email) |
| `DELETE /subscribe/{id}` | Unsubscribe |
| `GET /alerts/latest` | Recent alert packages (optional access token) |
| `registry.json` | Local registry (gitignored; created at runtime) |
| `alert_feed.jsonl` | Append-only feed of dispatched packages |

Tokens are **hashed at rest**. Access TTL ≈ 5 minutes; refresh TTL ≈ 7 days.
Rate limits apply per email and IP. Optional email mirror honors `NOTIFY_DRY_RUN`.

Every package sets `simulated=true` when any field is simulated. Evidence
bibcodes are copied only from CandidateScore — never invented.

**UI:** frontend-v2 (`:5174`) **Community push** rail and classic (`:5173`)
**Community alerts** panel. How-to: [`docs/community-subscribe.md`](../../docs/community-subscribe.md).
