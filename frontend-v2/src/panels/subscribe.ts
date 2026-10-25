/**
 * Community subscribe rail: webhook/email opt-in for ranked-candidate alerts.
 * Same POST /subscribe contract as classic frontend/.
 */
import strings from "../copy/strings.json";

type SubRow = {
  id?: string;
  label?: string | null;
  webhook_host?: string;
  has_webhook?: boolean;
  has_email?: boolean;
};

export function mountSubscribe(host: HTMLElement): () => void {
  host.innerHTML = `
    <div class="rail-block subscribe">
      <h2 class="rail-title">${strings.subscribeTitle}</h2>
      <p class="rail-hint">${strings.subscribeHint}</p>
      <p class="rail-hint subscribe-honesty">${strings.subscribeHonesty}</p>
      <form class="subscribe-form" data-role="form">
        <label class="subscribe-field">
          <span>${strings.subscribeWebhook}</span>
          <input name="webhook_url" type="url" placeholder="https://example.com/hook" autocomplete="off" />
        </label>
        <label class="subscribe-field">
          <span>${strings.subscribeEmail}</span>
          <input name="email" type="email" placeholder="you@observatory.edu" autocomplete="off" />
        </label>
        <label class="subscribe-field">
          <span>${strings.subscribeLabel}</span>
          <input name="label" type="text" placeholder="campus-0.3m" autocomplete="off" />
        </label>
        <button type="submit" class="scenario-btn subscribe-btn">${strings.subscribeSubmit}</button>
      </form>
      <p class="subscribe-status" data-role="status" aria-live="polite" hidden></p>
      <p class="rail-hint">
        ${strings.subscribeFeedHint}
        <a class="subscribe-feed-link" href="/alerts/latest" target="_blank" rel="noopener noreferrer">${strings.subscribeFeedLink}</a>
      </p>
      <ul class="subscribe-list" data-role="list"></ul>
    </div>
  `;

  const form = host.querySelector<HTMLFormElement>("[data-role=form]")!;
  const status = host.querySelector<HTMLElement>("[data-role=status]")!;
  const list = host.querySelector<HTMLUListElement>("[data-role=list]")!;

  async function refresh(): Promise<void> {
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
              r.webhook_host ? `hook:${r.webhook_host}` : "",
              r.has_email ? "email" : "",
            ].filter(Boolean);
            return `<li>${bits.join(" · ")}</li>`;
          })
          .join("");
      }
      if (data.notify_dry_run) {
        status.hidden = false;
        status.classList.remove("is-error", "is-ok");
        status.classList.add("is-info");
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
    status.classList.remove("is-error", "is-ok", "is-info");
    status.textContent = strings.subscribeWorking;
    try {
      const resp = await fetch("/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ webhook_url, email, label }),
      });
      const data = (await resp.json()) as {
        detail?: string | { msg?: string }[];
        notify_dry_run?: boolean;
        status?: string;
      };
      if (!resp.ok) {
        status.classList.add("is-error");
        const detail = data.detail;
        const msg =
          typeof detail === "string"
            ? detail
            : Array.isArray(detail)
              ? detail.map((d) => d.msg ?? String(d)).join("; ")
              : strings.subscribeFailed;
        status.textContent = msg || strings.subscribeFailed;
        return;
      }
      status.classList.add("is-ok");
      const dry =
        data.notify_dry_run === true
          ? ` ${strings.subscribeDryRunShort}`
          : "";
      status.textContent = `${strings.subscribeOk}${dry}`;
      form.reset();
      await refresh();
    } catch {
      status.classList.add("is-error");
      status.textContent = strings.subscribeFailed;
    }
  });

  void refresh();
  return () => {
    /* no WS subscription */
  };
}
