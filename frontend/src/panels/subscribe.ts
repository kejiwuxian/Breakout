/**
 * Community subscribe panel: access + refresh tokens over /ws/subscribe.
 */
import strings from "../copy/strings.json";

type SubRow = {
  id?: string;
  label?: string | null;
  email_masked?: string | null;
  has_email?: boolean;
  created_utc?: string;
};

const WS_URL =
  typeof location !== "undefined"
    ? `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/subscribe`
    : "ws://localhost:8000/ws/subscribe";

export function mountSubscribePanel(host: HTMLElement): () => void {
  host.innerHTML = `
    <section class="panel subscribe-panel" aria-labelledby="subscribe-title">
      <header class="panel-head">
        <h2 id="subscribe-title">${strings.subscribeTitle}</h2>
      </header>
      <p class="panel-hint">${strings.subscribeHint}</p>
      <form class="subscribe-form" data-role="issue-form">
        <label>
          <span>${strings.subscribeEmail}</span>
          <input name="email" type="email" placeholder="you@observatory.edu" autocomplete="email" />
        </label>
        <label>
          <span>${strings.subscribeLabel}</span>
          <input name="label" type="text" placeholder="My 0.3m scope" autocomplete="off" />
        </label>
        <button type="submit">${strings.subscribeIssue}</button>
      </form>
      <div class="subscribe-dry-tokens" data-role="tokens" hidden></div>
      <p class="subscribe-status" data-role="status" hidden></p>
      <p class="panel-hint" data-role="ws-status"></p>
      <p class="panel-hint">${strings.subscribeFeedHint}</p>
      <ul class="subscribe-list" data-role="list"></ul>
    </section>
  `;

  const form = host.querySelector<HTMLFormElement>("[data-role=issue-form]")!;
  const status = host.querySelector<HTMLElement>("[data-role=status]")!;
  const tokensEl = host.querySelector<HTMLElement>("[data-role=tokens]")!;
  const wsStatus = host.querySelector<HTMLElement>("[data-role=ws-status]")!;
  const list = host.querySelector<HTMLUListElement>("[data-role=list]")!;
  let ws: WebSocket | null = null;
  let refreshToken = "";
  let refreshTimer: number | null = null;

  function showStatus(ok: boolean, text: string): void {
    status.hidden = false;
    status.textContent = text;
    status.classList.toggle("is-error", !ok);
  }

  async function refreshList(): Promise<void> {
    try {
      const resp = await fetch("/subscribe", { cache: "no-store" });
      if (!resp.ok) return;
      const data = (await resp.json()) as { subscribers?: SubRow[] };
      const rows = data.subscribers ?? [];
      list.innerHTML = rows.length
        ? rows
            .map((r) => `<li>${r.label || r.id?.slice(0, 8)} · ${r.email_masked || ""}</li>`)
            .join("")
        : `<li class="muted">${strings.subscribeEmpty}</li>`;
    } catch {
      /* ignore */
    }
  }

  async function refreshAndExtend(socket: WebSocket): Promise<void> {
    if (!refreshToken) return;
    const resp = await fetch("/subscribe/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    const data = (await resp.json()) as {
      access_token?: string;
      refresh_token?: string;
      access_ttl_sec?: number;
    };
    if (!resp.ok || !data.access_token || !data.refresh_token) return;
    refreshToken = data.refresh_token;
    socket.send(JSON.stringify({ type: "access_token", access_token: data.access_token }));
    if (typeof data.access_ttl_sec === "number") {
      if (refreshTimer != null) window.clearTimeout(refreshTimer);
      refreshTimer = window.setTimeout(() => {
        void refreshAndExtend(socket);
      }, Math.max(1000, (data.access_ttl_sec - 30) * 1000));
    }
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(form);
    const email = String(fd.get("email") || "").trim() || null;
    const label = String(fd.get("label") || "").trim() || null;
    showStatus(true, strings.subscribeWorking);
    try {
      const resp = await fetch("/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, label }),
      });
      const data = (await resp.json()) as {
        access_token?: string;
        refresh_token?: string;
        access_expires_utc?: string;
        access_ttl_sec?: number;
        detail?: string;
      };
      if (!resp.ok || !data.access_token || !data.refresh_token) {
        showStatus(false, data.detail || strings.subscribeFailed);
        return;
      }
      refreshToken = data.refresh_token;
      tokensEl.hidden = false;
      tokensEl.textContent = `${strings.subscribeAccessToken}: ${data.access_token.slice(0, 12)}… · ${strings.subscribeRefreshToken}: ${data.refresh_token.slice(0, 12)}…`;
      showStatus(true, strings.subscribeIssueOk);
      if (ws) ws.close();
      ws = new WebSocket(`${WS_URL}?access_token=${encodeURIComponent(data.access_token)}`);
      ws.addEventListener("open", () => {
        wsStatus.textContent = strings.subscribeWsOpen;
      });
      ws.addEventListener("close", () => {
        wsStatus.textContent = strings.subscribeWsClosed;
      });
      ws.addEventListener("message", (msg) => {
        try {
          const frame = JSON.parse(String(msg.data)) as { type?: string; expires_in_sec?: number };
          if (frame.type === "subscribe_hello" || frame.type === "access_extended") {
            if (typeof frame.expires_in_sec === "number" && ws) {
              if (refreshTimer != null) window.clearTimeout(refreshTimer);
              refreshTimer = window.setTimeout(() => {
                if (ws) void refreshAndExtend(ws);
              }, Math.max(1000, (frame.expires_in_sec - 30) * 1000));
            }
          }
        } catch {
          /* ignore */
        }
      });
      await refreshList();
    } catch {
      showStatus(false, strings.subscribeFailed);
    }
  });

  void refreshList();
  return () => {
    if (refreshTimer != null) window.clearTimeout(refreshTimer);
    if (ws) ws.close();
  };
}
