/**
 * Community subscribe rail: two-token email confirm (no webhook).
 * POST /subscribe/request → dry-run tokens → POST /subscribe/confirm.
 */
import strings from "../copy/strings.json";

type SubRow = {
  id?: string;
  label?: string | null;
  email_masked?: string | null;
  has_email?: boolean;
  status?: string;
};

export function mountSubscribe(host: HTMLElement): () => void {
  host.innerHTML = `
    <div class="rail-block subscribe">
      <h2 class="rail-title">${strings.subscribeTitle}</h2>
      <p class="rail-hint">${strings.subscribeHint}</p>
      <p class="rail-hint subscribe-honesty">${strings.subscribeHonesty}</p>
      <p class="rail-hint subscribe-dry" data-role="dry" hidden></p>

      <form class="subscribe-form" data-role="request-form">
        <p class="subscribe-step">${strings.subscribeStep1}</p>
        <label class="subscribe-field">
          <span>${strings.subscribeEmail}</span>
          <input name="email" type="email" required placeholder="you@observatory.edu" autocomplete="email" />
        </label>
        <label class="subscribe-field">
          <span>${strings.subscribeLabel}</span>
          <input name="label" type="text" placeholder="campus-0.3m" autocomplete="off" />
        </label>
        <button type="submit" class="scenario-btn subscribe-btn">${strings.subscribeRequest}</button>
      </form>

      <div class="subscribe-dry-tokens" data-role="dry-tokens" hidden></div>

      <form class="subscribe-form subscribe-confirm-form" data-role="confirm-form">
        <p class="subscribe-step">${strings.subscribeStep2}</p>
        <label class="subscribe-field">
          <span>${strings.subscribeRequestToken}</span>
          <input name="request_token" type="text" required autocomplete="off" spellcheck="false" />
        </label>
        <label class="subscribe-field">
          <span>${strings.subscribeConfirmToken}</span>
          <input name="confirm_token" type="text" required autocomplete="off" spellcheck="false" />
        </label>
        <button type="submit" class="scenario-btn subscribe-btn">${strings.subscribeConfirm}</button>
      </form>

      <p class="subscribe-status" data-role="status" aria-live="polite" hidden></p>
      <p class="rail-hint">
        ${strings.subscribeFeedHint}
        <a class="subscribe-feed-link" href="/alerts/latest" target="_blank" rel="noopener noreferrer">${strings.subscribeFeedLink}</a>
      </p>
      <ul class="subscribe-list" data-role="list"></ul>
    </div>
  `;

  const requestForm = host.querySelector<HTMLFormElement>("[data-role=request-form]")!;
  const confirmForm = host.querySelector<HTMLFormElement>("[data-role=confirm-form]")!;
  const status = host.querySelector<HTMLElement>("[data-role=status]")!;
  const dryNote = host.querySelector<HTMLElement>("[data-role=dry]")!;
  const dryTokens = host.querySelector<HTMLElement>("[data-role=dry-tokens]")!;
  const list = host.querySelector<HTMLUListElement>("[data-role=list]")!;

  function showStatus(kind: "ok" | "error" | "info", text: string): void {
    status.hidden = false;
    status.classList.remove("is-error", "is-ok", "is-info");
    status.classList.add(`is-${kind}`);
    status.textContent = text;
  }

  function fillConfirmTokens(requestToken: string, confirmToken: string): void {
    const rt = confirmForm.elements.namedItem("request_token") as HTMLInputElement | null;
    const ct = confirmForm.elements.namedItem("confirm_token") as HTMLInputElement | null;
    if (rt) rt.value = requestToken;
    if (ct) ct.value = confirmToken;
  }

  function showDryTokens(requestToken: string, confirmToken: string, label: string): void {
    dryTokens.hidden = false;
    dryTokens.innerHTML = `
      <p class="subscribe-dry-label">${label || strings.subscribeDryTokensTitle}</p>
      <p class="subscribe-token-line"><span>${strings.subscribeRequestToken}</span>
        <code data-role="rt">${requestToken}</code></p>
      <p class="subscribe-token-line"><span>${strings.subscribeConfirmToken}</span>
        <code data-role="ct">${confirmToken}</code></p>
    `;
    fillConfirmTokens(requestToken, confirmToken);
  }

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
        dryNote.textContent = "";
      }
    } catch {
      /* offline panel — ignore */
    }
  }

  function detailMessage(data: { detail?: string | { msg?: string }[] }, fallback: string): string {
    const detail = data.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d) => d.msg ?? String(d)).join("; ");
    return fallback;
  }

  requestForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(requestForm);
    const email = String(fd.get("email") || "").trim();
    const label = String(fd.get("label") || "").trim() || null;
    showStatus("info", strings.subscribeWorking);
    dryTokens.hidden = true;
    dryTokens.innerHTML = "";
    try {
      const resp = await fetch("/subscribe/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, label }),
      });
      const data = (await resp.json()) as {
        detail?: string | { msg?: string }[];
        notify_dry_run?: boolean;
        pending?: boolean;
        request_id?: string;
        dry_run?: {
          label?: string;
          request_token?: string;
          confirm_token?: string;
        };
      };
      if (!resp.ok) {
        showStatus("error", detailMessage(data, strings.subscribeFailed));
        return;
      }
      const dry = data.dry_run;
      if (dry?.request_token && dry?.confirm_token) {
        showDryTokens(
          dry.request_token,
          dry.confirm_token,
          dry.label || strings.subscribeDryTokensTitle,
        );
        showStatus("ok", strings.subscribeRequestOkDry);
      } else {
        showStatus("ok", strings.subscribeRequestOk);
      }
    } catch {
      showStatus("error", strings.subscribeFailed);
    }
  });

  confirmForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(confirmForm);
    const request_token = String(fd.get("request_token") || "").trim();
    const confirm_token = String(fd.get("confirm_token") || "").trim();
    showStatus("info", strings.subscribeConfirmWorking);
    try {
      const resp = await fetch("/subscribe/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_token, confirm_token }),
      });
      const data = (await resp.json()) as {
        detail?: string | { msg?: string }[];
        status?: string;
        access_token?: string;
        subscriber?: { email_masked?: string };
      };
      if (!resp.ok) {
        showStatus("error", detailMessage(data, strings.subscribeConfirmFailed));
        return;
      }
      const masked = data.subscriber?.email_masked
        ? ` (${data.subscriber.email_masked})`
        : "";
      showStatus("ok", `${strings.subscribeConfirmOk}${masked}`);
      dryTokens.hidden = true;
      dryTokens.innerHTML = "";
      confirmForm.reset();
      requestForm.reset();
      await refresh();
    } catch {
      showStatus("error", strings.subscribeConfirmFailed);
    }
  });

  void refresh();
  return () => {
    /* no WS subscription */
  };
}
