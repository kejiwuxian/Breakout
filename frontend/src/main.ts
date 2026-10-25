/**
 * Project Supernova — primary mission UI (`frontend/`, port 5173).
 * Product IA from frontend-v2; visual system from the Supernova design guide.
 */
import "./style.css";
import strings from "./copy/strings.json";
import { mountAbout } from "./panels/about";
import { mountCandidates } from "./panels/candidates";
import { mountScenarios } from "./panels/scenarios";
import { mountSky } from "./panels/sky";
import { mountSourcesInfo, type SourceStatus } from "./panels/sources";
import { mountSubscribe } from "./panels/subscribe";
import { handleVoiceEvent, mountVoice, resetVoicePlayback } from "./panels/voice";
import {
  applyEvent,
  beginScenarioSwitch,
  getState,
  hydrateMission,
  packageMatchesScenario,
  setConnected,
  returnToLive,
  subscribe,
  type CandidateRow,
  type SkymapPayload,
} from "./state/store";
import { connectEvents } from "./ws/events";

type CommunityCandidate = CandidateRow & {
  evidence?: { bibcode: string; claim: string }[];
};

type LatestPackage = {
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

function packageToSkymap(pkg: LatestPackage): SkymapPayload | null {
  if (!pkg?.alert_id || !pkg.skymap) return null;
  const sky = pkg.skymap;
  return {
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
}

/**
 * Optionally seed skymap + candidates from /alerts/latest.
 * Default cold start stays empty (listening) — only hydrate with ?hydrate=1
 * or after a manual Replay start (onStarted).
 */
async function hydrateFromLatest(opts?: {
  /** Default true for page-load hydrate; false after Scenario Run so AOI zoom plays. */
  suppressZoom?: boolean;
  /** Only accept a package that belongs to this scenario (avoids stale flash). */
  scenarioId?: string;
  /** Reject if the user already started another scenario. */
  expectEpoch?: number;
}): Promise<boolean> {
  try {
    const res = await fetch("/alerts/latest", { cache: "no-store" });
    if (!res.ok) return false;
    const body = (await res.json()) as { packages?: LatestPackage[] };
    const packages = body.packages ?? [];
    const pkg = opts?.scenarioId
      ? packages.find((p) => packageMatchesScenario(p, opts.scenarioId!))
      : packages[0];
    if (!pkg) return false;
    const skymap = packageToSkymap(pkg);
    if (!skymap) return false;
    // WS may have already applied this alert — skip a redundant emit/zoom bump.
    const current = getState();
    if (
      current.skymap?.alert_id === skymap.alert_id &&
      current.candidates.length > 0
    ) {
      return true;
    }
    return hydrateMission({
      skymap,
      candidates: normalizeCandidates(pkg.candidates),
      simulated: Boolean(pkg.simulated ?? pkg.skymap?.simulated),
      suppressZoom: opts?.suppressZoom,
      expectEpoch: opts?.expectEpoch,
    });
  } catch {
    // Offline / empty feed — sky stays on waiting/empty until a live alert or Replay.
    return false;
  }
}

/** Poll until WS or a matching /alerts/latest package fills the mission. */
async function settleScenarioMission(
  scenarioId: string,
  expectEpoch: number,
): Promise<void> {
  for (let i = 0; i < 25; i++) {
    if (getState().missionEpoch !== expectEpoch) return;
    const { skymap, candidates } = getState();
    if (
      skymap &&
      packageMatchesScenario(
        { alert_id: skymap.alert_id, simulated: skymap.simulated },
        scenarioId,
      ) &&
      (candidates.length > 0 || i >= 8)
    ) {
      return;
    }
    const ok = await hydrateFromLatest({
      suppressZoom: false,
      scenarioId,
      expectEpoch,
    });
    if (ok) return;
    await new Promise((r) => setTimeout(r, 200));
  }
}

function isIdleScenario(scen: string | null | undefined): boolean {
  return !scen || scen === "live_waiting";
}

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) throw new Error("#app missing");

app.innerHTML = `
  <div class="app-shell">
    <header class="top-nav">
      <div class="nav-left">
        <a class="brand" href="#/" id="brand-link">${strings.brand}</a>
        <a class="nav-about" href="#/about" id="nav-about">${strings.navAbout}</a>
      </div>
      <div class="nav-right">
        <div class="status-cluster">
          <button type="button" class="source-status-trigger" id="source-status-trigger" aria-haspopup="dialog" aria-label="Data sources and connection status">
            <span class="status-dot" id="status-dot" aria-hidden="true"></span>
            <span class="status-text" id="status">Connecting to app…</span>
            <span class="source-status-info" aria-hidden="true">ⓘ</span>
          </button>
          <span class="badge sim" id="sim-badge" hidden>${strings.simulatedBadge}</span>
          <span class="badge hist" id="real-badge" hidden>${strings.realBadge}</span>
          <span class="badge live" id="live-badge" hidden>${strings.liveBadge}</span>
        </div>
      </div>
    </header>
    <div class="workspace" id="mission-view">
      <main class="main">
        <div class="page-chrome">
          <p class="page-category">${strings.pageCategory}</p>
          <h2 class="page-title">${strings.pageTitle}</h2>
        </div>
        <section class="sky-host" id="panel-sky" aria-label="${strings.skyTitle}"></section>
        <div class="event-guide">
          <p class="page-purpose">${strings.pagePurpose}</p>
          <button type="button" class="ghost-btn sky-reset" id="back-to-sky" aria-controls="sky-map-view">${strings.skyReset}</button>
        </div>
        <section class="event-select-host" id="panel-scenarios" aria-label="${strings.scenariosTitle}"></section>
        <p class="stage-foot">${strings.legacyNote}</p>
      </main>
      <aside class="rail" aria-label="Mission detail">
        <div id="panel-event-summary"></div>
        <div id="panel-candidates"></div>
        <div id="panel-subscribe"></div>
        <div id="panel-voice"></div>
      </aside>
    </div>
    <section
      class="about-view"
      id="about-view"
      hidden
      tabindex="-1"
      aria-label="${strings.aboutAria}"
    ></section>
  </div>
`;

const statusEl = document.querySelector<HTMLElement>("#status")!;
const statusDot = document.querySelector<HTMLElement>("#status-dot")!;
const statusTrigger = document.querySelector<HTMLButtonElement>("#source-status-trigger")!;
const simBadge = document.querySelector<HTMLElement>("#sim-badge")!;
const realBadge = document.querySelector<HTMLElement>("#real-badge")!;
const liveBadge = document.querySelector<HTMLElement>("#live-badge")!;
const summaryHost = document.querySelector<HTMLElement>("#panel-event-summary")!;
const missionView = document.querySelector<HTMLElement>("#mission-view")!;
const aboutView = document.querySelector<HTMLElement>("#about-view")!;
const brandLink = document.querySelector<HTMLAnchorElement>("#brand-link")!;
const aboutNav = document.querySelector<HTMLAnchorElement>("#nav-about")!;

let appConnection: "connecting" | "open" | "closed" = "connecting";
let sourceStatus: SourceStatus | null = null;
let pipelineProgress = "";

function renderConnectionStatus() {
  let label: string;
  if (appConnection === "connecting") {
    label = "Connecting to app…";
  } else if (appConnection === "closed") {
    label = "App connection offline";
  } else if (!sourceStatus) {
    label = "App connected · source status unverified";
  } else if (sourceStatus.mode === "cached") {
    label = "Connected";
  } else if (
    !sourceStatus.live_enabled ||
    sourceStatus.sources.every((source) =>
      ["reference", "disabled", "unconfigured"].includes(source.state),
    )
  ) {
    label = "App connected · live feeds unavailable";
  } else if (sourceStatus.sources.some((source) => source.state === "receiving")) {
    label = sourceStatus.sources.some((source) => source.science_alerts > 0)
      ? "Live neutrino alert received"
      : sourceStatus.sources.some((source) => source.test_notices > 0)
        ? "Live feed · service check received"
        : "Live feed message received";
  } else if (sourceStatus.sources.some((source) => source.state === "error")) {
    label = "App connected · live feed error";
  } else {
    label = "Live mode · awaiting feed";
  }
  statusEl.textContent = label;
  statusDot.classList.toggle("is-live", appConnection === "open");
  statusTrigger.setAttribute("aria-label", `${label}. Open data sources and connection details`);
  statusTrigger.title = [pipelineProgress, "View data sources and connection details"].filter(Boolean).join(" · ");
}

const sourcesInfo = mountSourcesInfo(statusTrigger, {
  onStatus(status) {
    sourceStatus = status;
    renderConnectionStatus();
  },
});

function updatePipelineProgress(detail: string) {
  pipelineProgress = detail;
  renderConnectionStatus();
}

mountAbout(aboutView);

/** Hash route: `#/about` shows About; anything else keeps the mission workspace. */
function routeFromHash(): "mission" | "about" {
  const raw = (window.location.hash || "").replace(/^#/, "").replace(/^\//, "");
  const path = raw.split("?")[0]?.toLowerCase() ?? "";
  return path === "about" ? "about" : "mission";
}

function applyRoute(route: "mission" | "about") {
  const onAbout = route === "about";
  missionView.hidden = onAbout;
  aboutView.hidden = !onAbout;
  aboutNav.setAttribute("aria-current", onAbout ? "page" : "false");
  brandLink.setAttribute("aria-current", onAbout ? "false" : "page");
  document.body.classList.toggle("view-about", onAbout);
  if (onAbout) {
    aboutView.focus({ preventScroll: true });
    aboutView.scrollTop = 0;
  }
}

function onHashChange() {
  applyRoute(routeFromHash());
}

window.addEventListener("hashchange", onHashChange);
applyRoute(routeFromHash());

aboutView.addEventListener("click", (ev) => {
  const target = ev.target as HTMLElement | null;
  if (target?.closest?.("[data-role='about-back']")) {
    // Let the hash link navigate; hashchange applies the route.
  }
});

let activeScenario: string | null = null;
let activeEpoch = 0;

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
  // Prefer the live skymap honesty bit over a possibly-stale lastSimulated
  // left by a prior scenario's WS frames.
  const simulatedBit =
    typeof skymap?.simulated === "boolean"
      ? skymap.simulated
      : typeof lastSimulated === "boolean"
        ? lastSimulated
        : undefined;
  const nature = natureLabel(simulatedBit, scenario ?? activeScenario);
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

mountSky(
  document.querySelector("#panel-sky")!,
  document.querySelector<HTMLButtonElement>("#back-to-sky")!,
  () => {
    activeScenario = null;
    resetVoicePlayback();
    activeEpoch = returnToLive(sourceStatus?.mode !== "cached");
    applyBadges(undefined);
    updatePipelineProgress("Waiting for an event");
  },
);
mountScenarios(document.querySelector("#panel-scenarios")!, {
  onScenario: (id) => {
    activeScenario = id;
    activeEpoch = beginScenarioSwitch(id);
  },
  onStarted: async (id) => {
    await settleScenarioMission(id, activeEpoch);
  },
});
mountCandidates(document.querySelector("#panel-candidates")!);
mountSubscribe(document.querySelector("#panel-subscribe")!);
mountVoice(document.querySelector("#panel-voice")!);
paintEventSummary();
subscribe(() => paintEventSummary());

if (wantsHydrateFromLatest()) {
  void hydrateFromLatest({ expectEpoch: getState().missionEpoch });
}

connectEvents(
  (event) => {
    if (!applyEvent(event)) return;
    if (event.type === "voice") handleVoiceEvent(event);

    if (event.type === "hello") {
      const scen = getState().scenario;
      if (!isIdleScenario(scen)) {
        activeScenario = scen ?? null;
        updatePipelineProgress(strings.connected);
      } else {
        activeScenario = null;
        updatePipelineProgress("Waiting for an event");
      }
    } else if (event.type === "alert") {
      updatePipelineProgress(`${strings.statusAlert}: ${String(
        (event.payload as { kind?: string })?.kind ?? "",
      )}`);
      applyBadges(event.simulated);
      void sourcesInfo.refresh();
    } else if (event.type === "skymap") {
      updatePipelineProgress(strings.statusSkymap);
      applyBadges(event.simulated);
    } else if (event.type === "candidates") {
      updatePipelineProgress(strings.statusCandidates);
      applyBadges(event.simulated);
    } else if (event.type === "voice") {
      const text = String((event.payload as { text?: string } | undefined)?.text ?? "");
      if (text) updatePipelineProgress(text);
      applyBadges(event.simulated);
    } else if (event.type === "scenario_done" && event.payload?.scenario) {
      activeScenario = String(event.payload.scenario);
      updatePipelineProgress(`${strings.scenarioStarted}: ${activeScenario}`);
    }
  },
  (state) => {
    appConnection = state;
    setConnected(state === "open");
    sourcesInfo.setConnection(state === "open");
    renderConnectionStatus();
  },
);
