/**
 * Subscribe to events — open access + refresh tokens over /ws/subscribe.
 * No prior credentials: POST /subscribe issues tokens to anyone.
 */
import strings from "../copy/strings.json";

const WS_URL =
  typeof location !== "undefined"
    ? `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/subscribe`
    : "ws://localhost:8000/ws/subscribe";

const API_ORIGIN =
  typeof location !== "undefined" ? `${location.protocol}//${location.host}` : "http://127.0.0.1:8000";

/** Copy-paste prompt for a third-party AI to write a subscribe relay script. */
export function buildRelayPrompt(opts: {
  apiOrigin: string;
  wsUrl: string;
}): string {
  const { apiOrigin, wsUrl } = opts;
  return `Write a production-ready Python 3 script that listens to Project Supernova / BREAKOUT community subscribe events and relays each ranked-candidate alert on a notification channel I choose.

Honesty / scope (do not invent otherwise):
- This is community follow-up for SN_BURST / HE_NEUTRINO candidate sets — NOT an official GCN notice and NOT a confirmed supernova detection service.
- Packages may include simulated=true (dry-run / replay). Always surface that flag in the relayed message.
- Schema name: breakout.community_alert.v1 (type breakout.ranked_candidates).
- No account is required. POST /subscribe mints tokens for any caller (rate-limited). Tokens are hashed at rest.

Parameterize these at the top of the script (CLI flags or env vars):
- BASE_URL (default ${apiOrigin})
- Optional LABEL for POST /subscribe (e.g. campus-0.3m)
- RELAY_CHANNEL ∈ {stdout, webhook, email, sms, phone_call, custom} — implement a clear plugin/hook so I can plug Twilio / SMTP / Pushover / etc. Ask me which channel and credentials before hard-coding secrets.
- Max candidates to include in the relay body (default 10)
- Dry-run mode that prints the would-be message without calling the channel API

Auth + keep-alive (two-token model):
1) Issue tokens:
   POST {BASE_URL}/subscribe
   Content-Type: application/json
   Body: {} or {"label":"<LABEL>"}
   Response fields: access_token (~5 min), refresh_token (~7 days), access_expires_utc, access_ttl_sec, ws=/ws/subscribe
2) Refresh before access expires (rotate refresh; old refresh cannot be reused):
   POST {BASE_URL}/subscribe/refresh
   Body: {"refresh_token":"<refresh_token>"}
   → new access_token + rotated refresh_token
3) Open the live WebSocket (prefer query string; first-frame auth is also OK):
   ws(s)://{host}/ws/subscribe?access_token=<access_token>
   Local default: ${wsUrl}
   Or connect without a query string and send first frame:
   {"type":"auth","access_token":"<access_token>"}
4) On subscribe_hello / access_extended, read expires_in_sec and schedule refresh ~30s before expiry.
5) After refresh, extend the live session without reconnecting:
   {"type":"access_token","access_token":"<new_access_token>"}
   Expect {"type":"access_extended", ...}
6) If access expires without a successful extend, the socket closes with code 4001 (access_token_expired). Re-issue or refresh + reconnect.
7) Optional REST: GET {BASE_URL}/alerts/latest (recent packages; optional Bearer / ?token=). DELETE {BASE_URL}/subscribe/{id} to unsubscribe. GET {BASE_URL}/subscribe lists masked subscriber metadata.

Events to handle:
{"type":"community_alert","payload":{…},"simulated":true|false}

Payload (breakout.community_alert.v1) includes:
- alert_id, kind, source, t0_utc, significance, simulated
- skymap: peak_ra_deg, peak_dec_deg, credible_90_deg2, components, simulated
- candidates[]: star_id, ra_deg, dec_deg, class, spectral_type, distance_kpc, p_sky, posterior, breakout, ir_followup, presn_watch, evidence[{bibcode,claim}], simulated, rank_confidence, rank_reasoning, composition, life_expectancy
- instrument_hint, note

Relay message requirements:
- Lead with alert_id, simulated flag, peak RA/Dec, n candidates
- List top ranked ICRS coords (rank, star_id, ra_deg, dec_deg, posterior/p_sky)
- Include instrument_hint verbatim when present
- Never invent ADS bibcodes; only forward evidence already on the candidate
- Log reconnects, refresh failures, and close codes

Implementation notes:
- Use websocket-client or websockets + requests/httpx
- Store refresh_token securely (file mode 0600 or OS keychain); never log full tokens
- Robust reconnect with backoff; re-auth after 4001
- Default BASE_URL for local dry-run: ${apiOrigin}
- Default WS for local dry-run: ${wsUrl}

Ask me which RELAY_CHANNEL to implement first and which credentials/env vars to expect, then produce the full script with a short README of how to run a dry-run against a local Breakout API.`;
}

export function mountSubscribe(host: HTMLElement): () => void {
  host.innerHTML = `
    <div class="rail-block subscribe">
      <h2 class="rail-title">${strings.subscribeTitle}</h2>
      <p class="rail-hint">${strings.subscribeHint}</p>
      <p class="rail-hint subscribe-open">${strings.subscribeOpen}</p>
      <p class="rail-hint subscribe-honesty">${strings.subscribeHonesty}</p>

      <div class="subscribe-docs" data-role="docs">
        <h3 class="subscribe-docs-title">${strings.subscribeDocsTitle}</h3>
        <ol class="subscribe-docs-list">
          <li>
            <strong>${strings.subscribeDocsIssueTitle}</strong>
            <p>${strings.subscribeDocsIssueBody}</p>
            <pre class="subscribe-code" data-role="code-issue"></pre>
          </li>
          <li>
            <strong>${strings.subscribeDocsRefreshTitle}</strong>
            <p>${strings.subscribeDocsRefreshBody}</p>
            <pre class="subscribe-code" data-role="code-refresh"></pre>
          </li>
          <li>
            <strong>${strings.subscribeDocsWsTitle}</strong>
            <p>${strings.subscribeDocsWsBody}</p>
            <pre class="subscribe-code" data-role="code-ws"></pre>
          </li>
          <li class="subscribe-docs-relay">
            <details class="subscribe-relay" data-role="relay">
              <summary>${strings.subscribeDocsRelayTitle}</summary>
              <p>${strings.subscribeDocsRelayHint}</p>
              <div class="subscribe-relay-toolbar">
                <button type="button" class="subscribe-copy-btn" data-role="copy-relay">${strings.subscribeDocsRelayCopy}</button>
              </div>
              <pre class="subscribe-code subscribe-relay-prompt" data-role="code-relay"></pre>
            </details>
          </li>
        </ol>
        <p class="rail-hint">
          ${strings.subscribeDocsLink}
          ·
          <a class="subscribe-feed-link" href="/alerts/latest" target="_blank" rel="noopener noreferrer">${strings.subscribeFeedLink}</a>
        </p>
      </div>

      <form class="subscribe-form" data-role="issue-form">
        <p class="subscribe-step">${strings.subscribeStepStart}</p>
        <label class="subscribe-field">
          <span>${strings.subscribeLabel}</span>
          <input name="label" type="text" placeholder="campus-0.3m" autocomplete="off" />
        </label>
        <button type="submit" class="scenario-btn subscribe-btn">${strings.subscribeIssue}</button>
      </form>

      <div class="subscribe-tokens" data-role="tokens" hidden></div>
      <p class="subscribe-ws-status" data-role="ws-status" aria-live="polite"></p>
      <div class="subscribe-alerts" data-role="alerts" aria-live="polite"></div>
      <p class="subscribe-status" data-role="status" aria-live="polite" hidden></p>
      <ul class="subscribe-list" data-role="list" hidden></ul>
    </div>
  `;

  const issueForm = host.querySelector<HTMLFormElement>("[data-role=issue-form]")!;
  const status = host.querySelector<HTMLElement>("[data-role=status]")!;
  const tokensEl = host.querySelector<HTMLElement>("[data-role=tokens]")!;
  const wsStatus = host.querySelector<HTMLElement>("[data-role=ws-status]")!;
  const alertsEl = host.querySelector<HTMLElement>("[data-role=alerts]")!;

  const codeIssue = host.querySelector<HTMLElement>("[data-role=code-issue]")!;
  const codeRefresh = host.querySelector<HTMLElement>("[data-role=code-refresh]")!;
  const codeWs = host.querySelector<HTMLElement>("[data-role=code-ws]")!;
  const codeRelay = host.querySelector<HTMLElement>("[data-role=code-relay]")!;
  const copyRelayBtn = host.querySelector<HTMLButtonElement>("[data-role=copy-relay]")!;

  codeIssue.textContent = `POST ${API_ORIGIN}/subscribe
Content-Type: application/json

{} 
# optional: {"label":"campus-0.3m"}
# → access_token (~5 min) + refresh_token (~7 days)
# No account or prior credentials required.`;

  codeRefresh.textContent = `POST ${API_ORIGIN}/subscribe/refresh
Content-Type: application/json

{"refresh_token":"<refresh_token>"}
# → new access_token (+ rotated refresh_token)
# Then send on the live WS before access expires.`;

  codeWs.textContent = `WS  ${WS_URL}?access_token=<access_token>

# first frame alternative:
{"type":"auth","access_token":"<access_token>"}

# extend before expiry:
{"type":"access_token","access_token":"<new_access_token>"}

# server pushes:
{"type":"community_alert","payload":{…}}

# access expired → close code 4001`;

  const relayPrompt = buildRelayPrompt({ apiOrigin: API_ORIGIN, wsUrl: WS_URL });
  codeRelay.textContent = relayPrompt;

  copyRelayBtn.addEventListener("click", async () => {
    const label = strings.subscribeDocsRelayCopy;
    const done = strings.subscribeDocsRelayCopied;
    try {
      await navigator.clipboard.writeText(relayPrompt);
      copyRelayBtn.textContent = done;
    } catch {
      // Fallback for non-secure contexts / denied clipboard.
      const range = document.createRange();
      range.selectNodeContents(codeRelay);
      const sel = window.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(range);
      copyRelayBtn.textContent = "Select + ⌘/Ctrl+C";
    }
    window.setTimeout(() => {
      copyRelayBtn.textContent = label;
    }, 1600);
  });

  let accessToken = "";
  let refreshToken = "";
  let ws: WebSocket | null = null;
  let refreshTimer: number | null = null;
  let closed = false;

  function showStatus(kind: "ok" | "error" | "info", text: string): void {
    status.hidden = false;
    status.classList.remove("is-error", "is-ok", "is-info");
    status.classList.add(`is-${kind}`);
    status.textContent = text;
  }

  function showTokens(access: string, refresh: string, expiresUtc: string): void {
    tokensEl.hidden = false;
    tokensEl.innerHTML = `
      <p class="subscribe-dry-label">${strings.subscribeTokensTitle}</p>
      <p class="subscribe-token-line"><span>${strings.subscribeAccessToken}</span>
        <code title="${access}">${access.slice(0, 16)}…</code></p>
      <p class="subscribe-token-line"><span>${strings.subscribeRefreshToken}</span>
        <code title="${refresh}">${refresh.slice(0, 16)}…</code></p>
      <p class="rail-hint">${strings.subscribeExpires}: ${expiresUtc || "—"}</p>
      <p class="rail-hint">${strings.subscribeTokensStore}</p>
    `;
  }

  function setWsStatus(text: string): void {
    wsStatus.textContent = text;
  }

  function clearRefreshTimer(): void {
    if (refreshTimer != null) {
      window.clearTimeout(refreshTimer);
      refreshTimer = null;
    }
  }

  function scheduleRefresh(expiresInSec: number): void {
    clearRefreshTimer();
    const waitMs = Math.max(1_000, (expiresInSec - 30) * 1000);
    refreshTimer = window.setTimeout(() => {
      void refreshAndExtend();
    }, waitMs);
  }

  async function refreshAndExtend(): Promise<void> {
    if (!refreshToken || closed) return;
    try {
      const resp = await fetch("/subscribe/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      const data = (await resp.json()) as {
        access_token?: string;
        refresh_token?: string;
        access_expires_utc?: string;
        access_ttl_sec?: number;
      };
      if (!resp.ok || !data.access_token || !data.refresh_token) {
        setWsStatus(strings.subscribeRefreshFailed);
        return;
      }
      accessToken = data.access_token;
      refreshToken = data.refresh_token;
      showTokens(accessToken, refreshToken, data.access_expires_utc || "");
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "access_token", access_token: accessToken }));
      }
      if (typeof data.access_ttl_sec === "number") {
        scheduleRefresh(data.access_ttl_sec);
      }
    } catch {
      setWsStatus(strings.subscribeRefreshFailed);
    }
  }

  function connectWs(token: string): void {
    if (ws) {
      try {
        ws.close();
      } catch {
        /* ignore */
      }
      ws = null;
    }
    setWsStatus(strings.subscribeWsConnecting);
    const socket = new WebSocket(`${WS_URL}?access_token=${encodeURIComponent(token)}`);
    ws = socket;
    socket.addEventListener("open", () => setWsStatus(strings.subscribeWsOpen));
    socket.addEventListener("close", (ev) => {
      if (ev.code === 4001) {
        setWsStatus(strings.subscribeWsExpired);
      } else {
        setWsStatus(strings.subscribeWsClosed);
      }
    });
    socket.addEventListener("message", (msg) => {
      try {
        const data = JSON.parse(String(msg.data)) as {
          type?: string;
          expires_in_sec?: number;
          payload?: { alert_id?: string; n_candidates?: number; simulated?: boolean };
        };
        if (data.type === "subscribe_hello" || data.type === "access_extended") {
          if (typeof data.expires_in_sec === "number") {
            scheduleRefresh(data.expires_in_sec);
          }
          if (data.type === "access_extended") {
            setWsStatus(strings.subscribeWsExtended);
          }
          return;
        }
        if (data.type === "community_alert") {
          const p = data.payload || {};
          const line = document.createElement("p");
          line.className = "subscribe-alert-line";
          line.textContent = `${strings.subscribeAlertPrefix} ${p.alert_id || "?"} · n=${
            p.n_candidates ?? "?"
          }${p.simulated ? " · simulated" : ""}`;
          alertsEl.prepend(line);
          while (alertsEl.childElementCount > 5) {
            alertsEl.lastElementChild?.remove();
          }
        }
      } catch {
        /* ignore */
      }
    });
  }

  function detailMessage(data: { detail?: string | { msg?: string }[] }, fallback: string): string {
    const detail = data.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d) => d.msg ?? String(d)).join("; ");
    return fallback;
  }

  issueForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(issueForm);
    const label = String(fd.get("label") || "").trim() || null;
    showStatus("info", strings.subscribeWorking);
    try {
      // Open subscribe: empty body is enough — no account or prior credentials.
      const resp = await fetch("/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label }),
      });
      const data = (await resp.json()) as {
        detail?: string | { msg?: string }[];
        access_token?: string;
        refresh_token?: string;
        access_expires_utc?: string;
        access_ttl_sec?: number;
        subscriber?: { id?: string };
      };
      if (!resp.ok || !data.access_token || !data.refresh_token) {
        showStatus("error", detailMessage(data, strings.subscribeFailed));
        return;
      }
      accessToken = data.access_token;
      refreshToken = data.refresh_token;
      showTokens(accessToken, refreshToken, data.access_expires_utc || "");
      showStatus("ok", strings.subscribeIssueOk);
      connectWs(accessToken);
      if (typeof data.access_ttl_sec === "number") {
        scheduleRefresh(data.access_ttl_sec);
      }
    } catch {
      showStatus("error", strings.subscribeFailed);
    }
  });

  return () => {
    closed = true;
    clearRefreshTimer();
    if (ws) {
      try {
        ws.close();
      } catch {
        /* ignore */
      }
    }
  };
}
