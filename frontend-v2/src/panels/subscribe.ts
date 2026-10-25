/**
 * Community subscribe rail: access + refresh tokens over /ws/subscribe.
 * POST /subscribe → tokens → open WS → refresh + send access_token to extend.
 */
import strings from "../copy/strings.json";

type SubRow = {
  id?: string;
  label?: string | null;
  email_masked?: string | null;
  has_email?: boolean;
  status?: string;
};

const WS_URL =
  typeof location !== "undefined"
    ? `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/subscribe`
    : "ws://localhost:8000/ws/subscribe";

export function mountSubscribe(host: HTMLElement): () => void {
  host.innerHTML = `
    <div class="rail-block subscribe">
      <h2 class="rail-title">${strings.subscribeTitle}</h2>
      <p class="rail-hint">${strings.subscribeHint}</p>
      <p class="rail-hint subscribe-honesty">${strings.subscribeHonesty}</p>
      <p class="rail-hint subscribe-dry" data-role="dry" hidden></p>

      <form class="subscribe-form" data-role="issue-form">
        <p class="subscribe-step">${strings.subscribeStep1}</p>
        <label class="subscribe-field">
          <span>${strings.subscribeEmail}</span>
          <input name="email" type="email" placeholder="you@observatory.edu" autocomplete="email" />
        </label>
        <label class="subscribe-field">
          <span>${strings.subscribeLabel}</span>
          <input name="label" type="text" placeholder="campus-0.3m" autocomplete="off" />
        </label>
        <button type="submit" class="scenario-btn subscribe-btn">${strings.subscribeIssue}</button>
      </form>

      <div class="subscribe-tokens" data-role="tokens" hidden></div>
      <p class="subscribe-ws-status" data-role="ws-status" aria-live="polite"></p>
      <div class="subscribe-alerts" data-role="alerts"></div>

      <p class="subscribe-status" data-role="status" aria-live="polite" hidden></p>
      <p class="rail-hint">
        ${strings.subscribeFeedHint}
        <a class="subscribe-feed-link" href="/alerts/latest" target="_blank" rel="noopener noreferrer">${strings.subscribeFeedLink}</a>
      </p>
      <ul class="subscribe-list" data-role="list"></ul>
    </div>
  `;

  const issueForm = host.querySelector<HTMLFormElement>("[data-role=issue-form]")!;
  const status = host.querySelector<HTMLElement>("[data-role=status]")!;
  const dryNote = host.querySelector<HTMLElement>("[data-role=dry]")!;
  const tokensEl = host.querySelector<HTMLElement>("[data-role=tokens]")!;
  const wsStatus = host.querySelector<HTMLElement>("[data-role=ws-status]")!;
  const alertsEl = host.querySelector<HTMLElement>("[data-role=alerts]")!;
  const list = host.querySelector<HTMLUListElement>("[data-role=list]")!;

  let accessToken = "";
  let refreshToken = "";
  let subscriberId = "";
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
        <code>${access.slice(0, 12)}…</code></p>
      <p class="subscribe-token-line"><span>${strings.subscribeRefreshToken}</span>
        <code>${refresh.slice(0, 12)}…</code></p>
      <p class="rail-hint">${strings.subscribeExpires}: ${expiresUtc}</p>
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
    // Refresh a bit before expiry so the wire stays up.
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
        detail?: string;
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
          access_expires_utc?: string;
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
          const li = document.createElement("p");
          li.className = "subscribe-alert-line";
          li.textContent = `${strings.subscribeAlertPrefix} ${p.alert_id || "?"} · n=${
            p.n_candidates ?? "?"
          }${p.simulated ? " · simulated" : ""}`;
          alertsEl.prepend(li);
          while (alertsEl.childElementCount > 5) {
            alertsEl.lastElementChild?.remove();
          }
        }
      } catch {
        /* ignore */
      }
    });
  }

  async function refreshList(): Promise<void> {
    try {
      const resp = await fetch("/subscribe", { cache: "no-store" });
      if (!resp.ok) return;
      const data = (await resp.json()) as {
        subscribers?: SubRow[];
        notify_dry_run?: boolean;
      };
      const rows = data.subscribers ?? [];
      if (!rows.length) {
        list.innerHTML = `<li class="muted">${strings.subscribeEmpty}</li>`;
      } else {
        list.innerHTML = rows
          .map((r) => {
            const bits = [
              r.label || r.id?.slice(0, 8) || "subscriber",
              r.email_masked || (r.has_email ? "email" : ""),
            ].filter(Boolean);
            return `<li>${bits.join(" · ")}</li>`;
          })
          .join("");
      }
      if (data.notify_dry_run) {
        dryNote.hidden = false;
        dryNote.textContent = strings.subscribeDryRun;
      } else {
        dryNote.hidden = true;
      }
    } catch {
      /* ignore */
    }
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
    const email = String(fd.get("email") || "").trim() || null;
    const label = String(fd.get("label") || "").trim() || null;
    showStatus("info", strings.subscribeWorking);
    try {
      const resp = await fetch("/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, label }),
      });
      const data = (await resp.json()) as {
        detail?: string | { msg?: string }[];
        access_token?: string;
        refresh_token?: string;
        access_expires_utc?: string;
        access_ttl_sec?: number;
        subscriber?: { id?: string; email_masked?: string };
      };
      if (!resp.ok || !data.access_token || !data.refresh_token) {
        showStatus("error", detailMessage(data, strings.subscribeFailed));
        return;
      }
      accessToken = data.access_token;
      refreshToken = data.refresh_token;
      subscriberId = data.subscriber?.id || "";
      showTokens(accessToken, refreshToken, data.access_expires_utc || "");
      showStatus(
        "ok",
        `${strings.subscribeIssueOk}${
          data.subscriber?.email_masked ? ` (${data.subscriber.email_masked})` : ""
        }`,
      );
      connectWs(accessToken);
      if (typeof data.access_ttl_sec === "number") {
        scheduleRefresh(data.access_ttl_sec);
      }
      await refreshList();
    } catch {
      showStatus("error", strings.subscribeFailed);
    }
  });

  void refreshList();
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
