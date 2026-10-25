import "./sources.css";

export type SourceInfo = {
  id: string;
  name: string;
  description: string;
  cadence: string;
  url: string;
  transport: "gcn" | "hop" | "reference";
  topic: string;
  state: "disabled" | "unconfigured" | "starting" | "receiving" | "error" | "reference";
  last_received_at: string | null;
  last_science_alert_at: string | null;
  last_test_at: string | null;
  science_alerts: number;
  test_notices: number;
  retractions: number;
};

export type SourceStatus = {
  mode: "cached" | "live";
  live_enabled: boolean;
  generated_at: string;
  last_science_alert_received_at: string | null;
  sources: SourceInfo[];
};

const states: Record<SourceInfo["state"], string> = {
  disabled: "Off in demo mode",
  unconfigured: "Not configured",
  starting: "Awaiting broker traffic",
  receiving: "Traffic received",
  error: "Feed unavailable",
  reference: "Catalog / reference",
};

function escape(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]!);
}

function time(value: string | null): string {
  if (!value) return "None since this server started";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Unavailable" : `${parsed.toLocaleString()} (${Intl.DateTimeFormat().resolvedOptions().timeZone})`;
}

function safeUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

/** The green light reports the app connection; this dialog explains feed evidence. */
export function mountSourcesInfo(
  trigger: HTMLButtonElement,
  options: { onStatus?: (status: SourceStatus | null) => void } = {},
): {
  setConnection(connected: boolean): void;
  refresh(): Promise<SourceStatus | null>;
  destroy(): void;
} {
  let connected = false;
  let status: SourceStatus | null = null;
  let unavailable = false;
  let destroyed = false;
  let request: AbortController | null = null;
  let polling: ReturnType<typeof setInterval> | undefined;
  const dialog = document.createElement("dialog");
  dialog.id = "data-sources-dialog";
  dialog.className = "sources-dialog";
  dialog.setAttribute("aria-labelledby", "sources-title");
  dialog.setAttribute("aria-describedby", "sources-intro");
  dialog.innerHTML = `
    <div class="sources-heading">
      <div><p class="sources-eyebrow">Signal transparency</p><h2 id="sources-title">Data sources & connection</h2></div>
      <button class="sources-close" type="button" aria-label="Close data sources" autofocus>×</button>
    </div>
    <div class="sources-content">
      <p id="sources-intro">Observatory alerts, catalog positions, and literature each have a different role. The green light shows your connection to this app, not a detected supernova.</p>
      <div class="sources-session" aria-live="polite"></div>
      <div class="sources-list"></div>
      <details class="sources-explainer">
        <summary>What the replays and rankings mean</summary>
        <p><strong>Historical:</strong> IceCube-170922A replays a recorded 2017 neutrino notice. It is not a new detection.</p>
        <p><strong>Simulated:</strong> The Galactic CCSN / Betelgeuse scenario models a synthetic burst. It is explicitly labeled and does not mean Betelgeuse is exploding.</p>
        <p><strong>Computed:</strong> Localization and ranked objects are this app's derived results. Literature claims link to ADS records; a ranked star is a follow-up candidate, not a confirmed source.</p>
      </details>
      <p class="sources-footnote">Public alerts are filtered candidates, not a continuous stream of every neutrino detected. Quiet periods are expected. Declared test and retraction notices do not start science ranking or community notifications.</p>
    </div>
    <div class="sources-actions"><span class="sources-updated"></span><button class="sources-refresh" type="button">Refresh status</button></div>
  `;
  document.body.appendChild(dialog);
  trigger.setAttribute("aria-controls", dialog.id);
  trigger.setAttribute("aria-haspopup", "dialog");
  trigger.setAttribute("aria-expanded", "false");
  const session = dialog.querySelector<HTMLDivElement>(".sources-session")!;
  const list = dialog.querySelector<HTMLDivElement>(".sources-list")!;
  const updated = dialog.querySelector<HTMLSpanElement>(".sources-updated")!;
  const refreshButton = dialog.querySelector<HTMLButtonElement>(".sources-refresh")!;
  const closeButton = dialog.querySelector<HTMLButtonElement>(".sources-close")!;

  function render() {
    const connection = connected ? "Connected" : "Disconnected";
    let mode = "Checking feed status…";
    let explanation = "Checking the server's actual configuration.";
    if (unavailable) {
      mode = "Feed status unverified";
      explanation = "The source status service could not be reached. No live-feed claim can be verified. Try Refresh status.";
    } else if (status?.mode === "cached") {
      mode = "Demo / cached mode";
      explanation = "Live observatory feeds are switched off on this server. Replays use historical records and simulated scenarios.";
    } else if (status?.mode === "live") {
      const live = status.sources.filter((row) => row.transport !== "reference");
      mode = live.some((row) => row.state === "receiving") ? "Live mode · traffic observed" : "Live mode · no receipt confirmed";
      explanation = "Source badges below show observed activity. Configured access alone does not confirm a broker connection or a science detection.";
    }
    session.innerHTML = `
      <dl><div><dt>Your app connection</dt><dd>${connection}</dd></div><div><dt>Observatory feed mode</dt><dd>${escape(mode)}</dd></div></dl>
      <p class="sources-mode-note">${escape(explanation)}</p>
      ${status && !unavailable ? `<p class="sources-receipt">Last accepted live science alert: <strong>${escape(time(status.last_science_alert_received_at))}</strong></p>` : ""}
    `;
    const openIds = new Set(Array.from(list.querySelectorAll<HTMLDetailsElement>("details[open]")).map((node) => node.dataset.source));
    list.innerHTML = status && !unavailable ? `
      <h3>Sources you can verify</h3>
      ${status.sources.map((row) => {
        const url = safeUrl(row.url);
        return `<details class="sources-source" data-source="${escape(row.id)}" ${openIds.has(row.id) ? "open" : ""}>
          <summary><span>${escape(row.name)}</span><span class="sources-state" data-state="${escape(row.state)}">${escape(states[row.state] ?? "Unverified")}</span></summary>
          <div class="sources-source-body"><p>${escape(row.description)}</p><p class="sources-cadence">${escape(row.cadence)}</p>
          ${row.transport !== "reference" ? `<dl><div><dt>Science alerts received</dt><dd>${row.science_alerts}</dd></div><div><dt>Test notices received</dt><dd>${row.test_notices}</dd></div></dl><p class="sources-receipt">Latest traffic: ${escape(time(row.last_received_at))}</p>${row.retractions ? `<p class="sources-receipt">Retractions excluded: ${row.retractions}</p>` : ""}` : ""}
          ${url ? `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">Official source ↗</a>` : ""}</div>
        </details>`;
      }).join("")}
    ` : "";
    updated.textContent = status && !unavailable ? `Checked ${new Date(status.generated_at).toLocaleTimeString()}` : "";
  }

  async function refresh(): Promise<SourceStatus | null> {
    request?.abort();
    const controller = new AbortController();
    request = controller;
    refreshButton.disabled = true;
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch("/api/data-sources", { cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error("Source status unavailable");
      const body = await response.json() as SourceStatus;
      if (!["cached", "live"].includes(body.mode) || !Array.isArray(body.sources)) throw new Error("Unsupported source status");
      if (destroyed || request !== controller) return null;
      status = body;
      unavailable = false;
      options.onStatus?.(body);
      render();
      return body;
    } catch {
      if (destroyed || request !== controller) return null;
      unavailable = true;
      options.onStatus?.(null);
      render();
      return null;
    } finally {
      clearTimeout(timeout);
      if (request === controller) refreshButton.disabled = false;
    }
  }

  function open() {
    if (dialog.open) return;
    render();
    dialog.showModal();
    trigger.setAttribute("aria-expanded", "true");
    void refresh();
    polling = setInterval(() => { void refresh(); }, 30000);
  }
  function onClose() {
    trigger.setAttribute("aria-expanded", "false");
    clearInterval(polling);
    trigger.focus({ preventScroll: true });
  }
  const close = () => dialog.close();
  const refreshClick = () => { void refresh(); };
  trigger.addEventListener("click", open);
  closeButton.addEventListener("click", close);
  refreshButton.addEventListener("click", refreshClick);
  dialog.addEventListener("close", onClose);
  render();
  void refresh();
  return {
    setConnection(value) { connected = value; if (dialog.open) render(); },
    refresh,
    destroy() {
      destroyed = true;
      request?.abort();
      clearInterval(polling);
      trigger.removeEventListener("click", open);
      trigger.removeAttribute("aria-controls");
      trigger.removeAttribute("aria-expanded");
      dialog.remove();
    },
  };
}
