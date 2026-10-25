/**
 * Actions tab: LCOGT dry-run JSON, HST/JWST ToO drafts, GCN Circular draft.
 */
import strings from "../copy/strings.json";
import { subscribe, type ActionsPayload } from "../state/store";

type TabId = "lcogt" | "hst" | "jwst" | "gcn";

function pre(text: string): string {
  const el = document.createElement("pre");
  el.className = "actions-pre";
  el.textContent = text;
  return el.outerHTML;
}

export function mountActionsPanel(host: HTMLElement): () => void {
  host.innerHTML = `
    <section class="panel actions-panel" aria-labelledby="actions-title">
      <header class="panel-head">
        <h2 id="actions-title">${strings.actionsTitle}</h2>
        <span class="badge simulated" data-role="sim" hidden title="${strings.tooltipSimulated}">${strings.simulatedBadge}</span>
      </header>
      <p class="panel-hint">${strings.actionsHint}</p>
      <p class="panel-empty" data-role="empty">${strings.actionsEmpty}</p>
      <div class="actions-body" data-role="body" hidden>
        <p class="actions-meta" data-role="meta"></p>
        <div class="actions-tabs" role="tablist">
          <button type="button" role="tab" data-tab="lcogt" aria-selected="true">${strings.actionsTabLcogt}</button>
          <button type="button" role="tab" data-tab="hst" aria-selected="false">${strings.actionsTabHst}</button>
          <button type="button" role="tab" data-tab="jwst" aria-selected="false">${strings.actionsTabJwst}</button>
          <button type="button" role="tab" data-tab="gcn" aria-selected="false">${strings.actionsTabGcn}</button>
        </div>
        <div class="actions-pane" data-role="pane"></div>
      </div>
    </section>
  `;

  const empty = host.querySelector<HTMLElement>("[data-role=empty]")!;
  const body = host.querySelector<HTMLElement>("[data-role=body]")!;
  const meta = host.querySelector<HTMLElement>("[data-role=meta]")!;
  const pane = host.querySelector<HTMLElement>("[data-role=pane]")!;
  const simBadge = host.querySelector<HTMLElement>("[data-role=sim]")!;
  const tabs = [...host.querySelectorAll<HTMLButtonElement>("button[data-tab]")];

  let active: TabId = "lcogt";
  let current: ActionsPayload | null = null;

  function renderPane(): void {
    if (!current) {
      pane.innerHTML = "";
      return;
    }
    if (active === "lcogt") {
      const rg = current.lcogt?.request_group ?? null;
      const dry = current.lcogt?.dry_run ?? current.lcogt_dry_run;
      const head = dry
        ? strings.actionsLcogtDry
        : strings.actionsLcogtLive;
      pane.innerHTML = `<p class="actions-sub">${head}</p>${pre(
        rg ? JSON.stringify(rg, null, 2) : strings.actionsMissing,
      )}`;
      return;
    }
    if (active === "hst") {
      pane.innerHTML = pre(current.too_hst_markdown || strings.actionsMissing);
      return;
    }
    if (active === "jwst") {
      pane.innerHTML = pre(current.too_jwst_markdown || strings.actionsMissing);
      return;
    }
    pane.innerHTML = pre(current.gcn_circular_markdown || strings.actionsMissing);
  }

  function setTab(id: TabId): void {
    active = id;
    for (const btn of tabs) {
      const on = btn.dataset.tab === id;
      btn.setAttribute("aria-selected", on ? "true" : "false");
    }
    renderPane();
  }

  for (const btn of tabs) {
    btn.addEventListener("click", () => {
      const id = btn.dataset.tab as TabId;
      if (id) setTab(id);
    });
  }

  return subscribe((state) => {
    current = state.actions;
    const hasDrafts = Boolean(
      current?.lcogt ||
        current?.too_hst_markdown ||
        current?.too_jwst_markdown ||
        current?.gcn_circular_markdown,
    );
    empty.hidden = hasDrafts;
    body.hidden = !hasDrafts;
    simBadge.hidden = !(state.actionsSimulated || current?.simulated);
    if (!hasDrafts || !current) return;

    const top = current.top_star_id ? ` · top ${current.top_star_id}` : "";
    const dry = current.lcogt_dry_run ? strings.actionsDryBadge : "";
    meta.textContent = `${strings.actionsAlert} ${current.alert_id ?? "—"}${top}${dry ? ` · ${dry}` : ""}`;
    renderPane();
  });
}
