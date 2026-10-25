/**
 * Project Supernova — primary mission UI (`frontend/`, port 5173).
 * Product IA from frontend-v2; visual system from the Supernova design guide.
 */
import "./style.css";
import strings from "./copy/strings.json";
import { mountCandidates } from "./panels/candidates";
import { mountScenarios } from "./panels/scenarios";
import { mountSky } from "./panels/sky";
import { mountSubscribe } from "./panels/subscribe";
import { handleVoiceEvent, mountVoice } from "./panels/voice";
import {
  applyEvent,
  getState,
  hydrateMission,
  setConnected,
  subscribe,
  type CandidateRow,
  type SkymapPayload,
} from "./state/store";
import { connectEvents } from "./ws/events";

type CommunityCandidate = CandidateRow & {
  evidence?: { bibcode: string; claim: string }[];
};

/** Normalize community-alert rows into CandidateRow (lit + v1.1 fields). */
function normalizeCandidates(rows: CommunityCandidate[] | undefined): CandidateRow[] {
  if (!rows?.length) return [];
  return rows.map((row) => {
    const evidence =
      row.lit?.evidence?.length
        ? row.lit.evidence
        : (row.evidence ?? []).filter((e) => e?.bibcode && e?.claim);
    const lit = row.lit ?? {
      mass_loss: 0,
      variability: 0,
      evolved_stage: 0,
      confidence:
        typeof row.rank_confidence === "number" ? row.rank_confidence : 0,
      evidence,
    };
    return {
      ...row,
      lit: {
        ...lit,
        evidence,
      },
    };
  });
}

/** True when URL asks to seed UI from a prior /alerts/latest package. */
function wantsHydrateFromLatest(): boolean {
  try {
    return new URLSearchParams(window.location.search).get("hydrate") === "1";
  } catch {
    return false;
  }
}

/**
 * Optionally seed skymap + candidates from /alerts/latest.
 * Default cold start stays empty (listening) — only hydrate with ?hydrate=1
 * or after a manual Replay start (onStarted).
 */
async function hydrateFromLatest(opts?: {
  /** Default true for page-load hydrate; false after Scenario Run so AOI zoom plays. */
  suppressZoom?: boolean;
}): Promise<void> {
  try {
    const res = await fetch("/alerts/latest", { cache: "no-store" });
    if (!res.ok) return;
    const body = (await res.json()) as {
      packages?: Array<{
        alert_id?: string;
        simulated?: boolean;
        skymap?: {
          peak_ra_deg?: number;
          peak_dec_deg?: number;
          credible_90_deg2?: number;
          components?: string[];
          simulated?: boolean;
        };
        candidates?: CommunityCandidate[];
      }>;
    };
    const pkg = body.packages?.[0];
    if (!pkg?.alert_id || !pkg.skymap) return;
    const sky = pkg.skymap;
    const skymap: SkymapPayload = {
      alert_id: pkg.alert_id,
      nside: 64,
      ordering: "NESTED",
      frame: "ICRS",
      prob_path: `data/run/${pkg.alert_id}/skymap.fits`,
      components: sky.components ?? [],
      credible_90_deg2: Number(sky.credible_90_deg2 ?? 0),
      peak: {
        ra_deg: Number(sky.peak_ra_deg ?? 0),
        dec_deg: Number(sky.peak_dec_deg ?? 0),
      },
      simulated: Boolean(sky.simulated ?? pkg.simulated),
    };
    hydrateMission({
      skymap,
      candidates: normalizeCandidates(pkg.candidates),
      simulated: Boolean(pkg.simulated ?? sky.simulated),
      suppressZoom: opts?.suppressZoom,
    });
  } catch {
    // Offline / empty feed — sky stays on waiting/empty until a live alert or Replay.
  }
}

function isIdleScenario(scen: string | null | undefined): boolean {
  return !scen || scen === "live_waiting";
}

function statusListening(): string {
  return strings.listening ?? strings.connected;
}

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) throw new Error("#app missing");

app.innerHTML = `
  <div class="app-shell">
    <header class="top-nav">
      <h1 class="brand">${strings.brand}</h1>
      <div class="nav-right">
        <div class="status-cluster">
          <span class="status-dot" id="status-dot" aria-hidden="true"></span>
          <p class="status-text" id="status">${strings.connecting}</p>
          <span class="badge sim" id="sim-badge" hidden>${strings.simulatedBadge}</span>
          <span class="badge hist" id="real-badge" hidden>${strings.realBadge}</span>
          <span class="badge live" id="live-badge" hidden>${strings.liveBadge}</span>
        </div>
      </div>
    </header>
    <div class="workspace">
      <main class="main">
        <div class="page-chrome">
          <p class="page-category">${strings.pageCategory}</p>
          <h2 class="page-title">${strings.pageTitle}</h2>
          <p class="page-purpose">${strings.pagePurpose}</p>
        </div>
        <section class="event-select-host" id="panel-scenarios" aria-label="${strings.scenariosTitle}"></section>
        <section class="sky-host" id="panel-sky" aria-label="${strings.skyTitle}"></section>
        <p class="stage-foot">${strings.legacyNote}</p>
      </main>
      <aside class="rail" aria-label="Mission detail">
        <div id="panel-event-summary"></div>
        <div id="panel-candidates"></div>
        <div id="panel-subscribe"></div>
        <div id="panel-voice"></div>
      </aside>
    </div>
  </div>
`;

const statusEl = document.querySelector<HTMLElement>("#status")!;
const statusDot = document.querySelector<HTMLElement>("#status-dot")!;
const simBadge = document.querySelector<HTMLElement>("#sim-badge")!;
const realBadge = document.querySelector<HTMLElement>("#real-badge")!;
const liveBadge = document.querySelector<HTMLElement>("#live-badge")!;
const summaryHost = document.querySelector<HTMLElement>("#panel-event-summary")!;

let activeScenario: string | null = null;

function natureLabel(simulated: boolean | undefined, scenarioHint?: string | null): "sim" | "hist" | "live" | "unknown" {
  const scen = scenarioHint ?? activeScenario;
  if (simulated === true) return "sim";
  if (simulated === false) {
    const isB =
      scen === "scenario_b_icecube_170922a" ||
      (typeof scen === "string" && scen.toLowerCase().includes("icecube"));
    return isB ? "hist" : "live";
  }
  return "unknown";
}

function applyBadges(simulated: boolean | undefined, scenarioHint?: string | null) {
  const kind = natureLabel(simulated, scenarioHint);
  simBadge.hidden = kind !== "sim";
  realBadge.hidden = kind !== "hist";
  liveBadge.hidden = kind !== "live";
}

function paintEventSummary() {
  const { skymap, candidates, lastSimulated, scenario } = getState();
  const nature = natureLabel(
    typeof lastSimulated === "boolean" ? lastSimulated : skymap?.simulated,
    scenario ?? activeScenario,
  );
  const natureText =
    nature === "sim"
      ? strings.simulatedBadge
      : nature === "hist"
        ? strings.realBadge
        : nature === "live"
          ? strings.liveBadge
          : strings.unknownNature;

  summaryHost.innerHTML = `
    <div class="rail-block event-summary-block">
      <h2 class="rail-title">${strings.eventSummaryTitle}</h2>
      <div class="event-summary">
        <div class="event-summary-row">
          <span class="label">${strings.summaryAlert}</span>
          <span class="value">${skymap?.alert_id ?? strings.noData}</span>
        </div>
        <div class="event-summary-row">
          <span class="label">${strings.summaryNature}</span>
          <span class="value">${natureText}</span>
        </div>
        <div class="event-summary-row">
          <span class="label">${strings.summaryArea}</span>
          <span class="value">${
            skymap
              ? `${skymap.credible_90_deg2.toFixed(1)} deg²`
              : strings.noData
          }</span>
        </div>
        <div class="event-summary-row">
          <span class="label">${strings.summaryPeak}</span>
          <span class="value">${
            skymap
              ? `RA ${skymap.peak.ra_deg.toFixed(2)}° · Dec ${skymap.peak.dec_deg.toFixed(2)}°`
              : strings.noData
          }</span>
        </div>
        <div class="event-summary-row">
          <span class="label">${strings.summaryCandidates}</span>
          <span class="value">${candidates.length ? String(candidates.length) : strings.noData}</span>
        </div>
      </div>
    </div>
  `;
}

mountSky(document.querySelector("#panel-sky")!);
mountScenarios(document.querySelector("#panel-scenarios")!, {
  onScenario: (id) => {
    activeScenario = id;
  },
  onStarted: async () => {
    // Brief settle so community notify package is written, then refresh UI
    // even when the websocket is offline — without suppressing AOI zoom.
    await new Promise((r) => setTimeout(r, 400));
    await hydrateFromLatest({ suppressZoom: false });
  },
});
mountCandidates(document.querySelector("#panel-candidates")!);
mountSubscribe(document.querySelector("#panel-subscribe")!);
mountVoice(document.querySelector("#panel-voice")!);
paintEventSummary();
subscribe(() => paintEventSummary());

if (wantsHydrateFromLatest()) {
  void hydrateFromLatest();
}

connectEvents(
  (event) => {
    applyEvent(event);
    if (event.type === "voice") handleVoiceEvent(event);

    if (event.type === "hello") {
      const scen = (event as { scenario?: string }).scenario;
      if (!isIdleScenario(scen)) {
        activeScenario = scen ?? null;
        statusEl.textContent = strings.connected;
      } else {
        activeScenario = null;
        statusEl.textContent = statusListening();
      }
    } else if (event.type === "alert") {
      statusEl.textContent = `${strings.statusAlert}: ${String(
        (event.payload as { kind?: string })?.kind ?? "",
      )}`;
      applyBadges(event.simulated);
    } else if (event.type === "skymap") {
      statusEl.textContent = strings.statusSkymap;
      applyBadges(event.simulated);
    } else if (event.type === "candidates") {
      statusEl.textContent = strings.statusCandidates;
      applyBadges(event.simulated);
    } else if (event.type === "voice") {
      const text = String((event.payload as { text?: string } | undefined)?.text ?? "");
      if (text) statusEl.textContent = text;
      applyBadges(event.simulated);
    } else if (event.type === "scenario_done" && event.payload?.scenario) {
      activeScenario = String(event.payload.scenario);
      statusEl.textContent = `${strings.scenarioStarted}: ${activeScenario}`;
    }
  },
  (state) => {
    setConnected(state === "open");
    statusDot.classList.toggle("is-live", state === "open");
    if (state === "connecting") statusEl.textContent = strings.connecting;
    if (state === "open") {
      statusEl.textContent = isIdleScenario(activeScenario)
        ? statusListening()
        : strings.connected;
    }
    if (state === "closed") statusEl.textContent = strings.disconnected;
  },
);
