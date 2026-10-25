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
