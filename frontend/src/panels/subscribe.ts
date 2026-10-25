/**
 * Community subscribe panel: webhook/email opt-in for ranked-candidate alerts.
 */
import strings from "../copy/strings.json";

type SubRow = {
  id?: string;
  label?: string | null;
  webhook_host?: string;
  has_webhook?: boolean;
  has_email?: boolean;
  created_utc?: string;
};

export function mountSubscribePanel(host: HTMLElement): () => void {
  host.innerHTML = `
    <section class="panel subscribe-panel" aria-labelledby="subscribe-title">
      <header class="panel-head">
        <h2 id="subscribe-title">${strings.subscribeTitle}</h2>
      </header>
      <p class="panel-hint">${strings.subscribeHint}</p>
      <form class="subscribe-form" data-role="form">
        <label>
          <span>${strings.subscribeWebhook}</span>
          <input name="webhook_url" type="url" placeholder="https://example.com/hook" autocomplete="off" />
        </label>
        <label>
          <span>${strings.subscribeEmail}</span>
          <input name="email" type="email" placeholder="you@observatory.edu" autocomplete="off" />
        </label>
        <label>
          <span>${strings.subscribeLabel}</span>
          <input name="label" type="text" placeholder="My 0.3m scope" autocomplete="off" />
        </label>
        <button type="submit">${strings.subscribeSubmit}</button>
      </form>
      <p class="subscribe-status" data-role="status" hidden></p>
      <p class="panel-hint">${strings.subscribeFeedHint}</p>
      <ul class="subscribe-list" data-role="list"></ul>
    </section>
  `;

  const form = host.querySelector<HTMLFormElement>("[data-role=form]")!;
  const status = host.querySelector<HTMLElement>("[data-role=status]")!;
  const list = host.querySelector<HTMLUListElement>("[data-role=list]")!;

  async function refresh(): Promise<void> {
    try {
      const resp = await fetch("/subscribe");
      if (!resp.ok) return;
      const data = (await resp.json()) as {
        subscribers?: SubRow[];
        notify_dry_run?: boolean;
      };
      const rows = data.subscribers ?? [];
      list.innerHTML = rows
        .map((r) => {
          const bits = [
            r.label || r.id?.slice(0, 8) || "subscriber",
            r.webhook_host ? `hook:${r.webhook_host}` : "",
            r.has_email ? "email" : "",
          ].filter(Boolean);
          return `<li>${bits.join(" · ")}</li>`;
        })
        .join("");
      if (!rows.length) {
        list.innerHTML = `<li class="muted">${strings.subscribeEmpty}</li>`;
      }
      if (data.notify_dry_run) {
        status.hidden = false;
        status.textContent = strings.subscribeDryRun;
      }
    } catch {
      /* offline panel — ignore */
    }
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(form);
    const webhook_url = String(fd.get("webhook_url") || "").trim() || null;
    const email = String(fd.get("email") || "").trim() || null;
    const label = String(fd.get("label") || "").trim() || null;
    status.hidden = false;
    status.textContent = strings.subscribeWorking;
    try {
      const resp = await fetch("/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ webhook_url, email, label }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        status.textContent = String(data.detail || strings.subscribeFailed);
        return;
      }
      status.textContent = strings.subscribeOk;
      form.reset();
      await refresh();
    } catch {
      status.textContent = strings.subscribeFailed;
    }
  });

  void refresh();
  return () => {
    /* no WS subscription */
  };
}
