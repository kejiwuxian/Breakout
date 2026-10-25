# Event subscribers (Phase 1 MVP)

**Open access:** anyone can `POST /subscribe` (no account) to mint **access +
refresh** tokens, then receive ranked-candidate alerts on **`/ws/subscribe`**.

| Path | Role |
| --- | --- |
| `POST /subscribe` | Issue access_token + refresh_token (empty body OK) |
| `POST /subscribe/refresh` | Rotate tokens; send new access on live WS to extend |
| `WS /ws/subscribe` | Live push; auto-closes when access expires (code 4001) |
| `GET /subscribe` | List active subscriber metadata |
| `DELETE /subscribe/{id}` | Unsubscribe |
| `GET /alerts/latest` | Recent alert packages |
| `registry.json` | Local registry (gitignored) |
| `alert_feed.jsonl` | Append-only feed |

How-to: [`docs/community-subscribe.md`](../../docs/community-subscribe.md).
