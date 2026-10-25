/**
 * Community subscribe panel: two-token email confirm (no webhook).
 */
import strings from "../copy/strings.json";

type SubRow = {
  id?: string;
  label?: string | null;
  email_masked?: string | null;
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
      <form class="subscribe-form" data-role="request-form">
        <p class="subscribe-step">${strings.subscribeStep1}</p>
        <label>
          <span>${strings.subscribeEmail}</span>
          <input name="email" type="email" required placeholder="you@observatory.edu" autocomplete="email" />
        </label>
        <label>
          <span>${strings.subscribeLabel}</span>
          <input name="label" type="text" placeholder="My 0.3m scope" autocomplete="off" />
        </label>
        <button type="submit">${strings.subscribeRequest}</button>
      </form>
      <div class="subscribe-dry-tokens" data-role="dry-tokens" hidden></div>
      <form class="subscribe-form" data-role="confirm-form">
        <p class="subscribe-step">${strings.subscribeStep2}</p>
        <label>
          <span>${strings.subscribeRequestToken}</span>
          <input name="request_token" type="text" required autocomplete="off" spellcheck="false" />
        </label>
        <label>
          <span>${strings.subscribeConfirmToken}</span>
          <input name="confirm_token" type="text" required autocomplete="off" spellcheck="false" />
        </label>
        <button type="submit">${strings.subscribeConfirm}</button>
      </form>
      <p class="subscribe-status" data-role="status" hidden></p>
      <p class="panel-hint">${strings.subscribeFeedHint}</p>
      <ul class="subscribe-list" data-role="list"></ul>
    </section>
  `;

  const requestForm = host.querySelector<HTMLFormElement>("[data-role=request-form]")!;
  const confirmForm = host.querySelector<HTMLFormElement>("[data-role=confirm-form]")!;
  const status = host.querySelector<HTMLElement>("[data-role=status]")!;
  const dryTokens = host.querySelector<HTMLElement>("[data-role=dry-tokens]")!;
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
            r.email_masked || (r.has_email ? "email" : ""),
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

  requestForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(requestForm);
    const email = String(fd.get("email") || "").trim();
    const label = String(fd.get("label") || "").trim() || null;
    status.hidden = false;
    status.textContent = strings.subscribeWorking;
    dryTokens.hidden = true;
    dryTokens.innerHTML = "";
    try {
      const resp = await fetch("/subscribe/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, label }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        status.textContent = String(data.detail || strings.subscribeFailed);
        return;
      }
      const dry = data.dry_run as
        | { label?: string; request_token?: string; confirm_token?: string }
        | undefined;
      if (dry?.request_token && dry?.confirm_token) {
        dryTokens.hidden = false;
        dryTokens.innerHTML = `
          <p>${dry.label || strings.subscribeDryTokensTitle}</p>
          <p><code>${dry.request_token}</code></p>
          <p><code>${dry.confirm_token}</code></p>
        `;
        (confirmForm.elements.namedItem("request_token") as HTMLInputElement).value =
          dry.request_token;
        (confirmForm.elements.namedItem("confirm_token") as HTMLInputElement).value =
          dry.confirm_token;
        status.textContent = strings.subscribeRequestOkDry;
      } else {
        status.textContent = strings.subscribeRequestOk;
      }
    } catch {
      status.textContent = strings.subscribeFailed;
    }
  });

  confirmForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(confirmForm);
    const request_token = String(fd.get("request_token") || "").trim();
    const confirm_token = String(fd.get("confirm_token") || "").trim();
    status.hidden = false;
    status.textContent = strings.subscribeConfirmWorking;
    try {
      const resp = await fetch("/subscribe/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_token, confirm_token }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        status.textContent = String(data.detail || strings.subscribeConfirmFailed);
        return;
      }
      status.textContent = strings.subscribeConfirmOk;
      dryTokens.hidden = true;
      dryTokens.innerHTML = "";
      confirmForm.reset();
      requestForm.reset();
      await refresh();
    } catch {
      status.textContent = strings.subscribeConfirmFailed;
    }
  });

  void refresh();
  return () => {
    /* no WS subscription */
  };
}
