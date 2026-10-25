/**
 * BREAKOUT frontend-v2 — redesigned mission UI.
 * Same backend contracts as frontend/; does not replace the classic dashboard.
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
  hydrateMission,
  setConnected,
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

/** Load the latest community alert so the sky panel has a default Mollweide. */
async function hydrateFromLatest(opts?: {
  /** Default true for page load; false after Scenario Run so AOI zoom plays. */
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
    // Offline / empty feed — sky stays on empty state until a scenario runs.
  }
}

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) throw new Error("#app missing");

app.innerHTML = `
  <div class="shell">
    <main class="stage">
      <header class="stage-top">
        <div class="brand-block">
          <h1 class="brand">${strings.brand}</h1>
          <p class="tagline">${strings.tagline}</p>
          <p class="hero-support">${strings.heroSupport}</p>
        </div>
        <div class="status-cluster">
          <span class="status-dot" id="status-dot" aria-hidden="true"></span>
          <p class="status-text" id="status">${strings.connecting}</p>
          <span class="badge sim" id="sim-badge" hidden>${strings.simulatedBadge}</span>
          <span class="badge real" id="real-badge" hidden>${strings.realBadge}</span>
        </div>
      </header>
      <section class="sky-host" id="panel-sky" aria-label="${strings.skyTitle}"></section>
      <p class="stage-foot">${strings.legacyNote}</p>
    </main>
    <aside class="rail" aria-label="Mission controls">
      <div id="panel-scenarios"></div>
      <div id="panel-candidates"></div>
      <div id="panel-subscribe"></div>
      <div id="panel-voice"></div>
    </aside>
  </div>
`;

const statusEl = document.querySelector<HTMLElement>("#status")!;
const statusDot = document.querySelector<HTMLElement>("#status-dot")!;
const simBadge = document.querySelector<HTMLElement>("#sim-badge")!;
const realBadge = document.querySelector<HTMLElement>("#real-badge")!;

let activeScenario: string | null = null;

function applyBadges(simulated: boolean | undefined, scenarioHint?: string | null) {
  const scen = scenarioHint ?? activeScenario;
  const isB =
    scen === "scenario_b_icecube_170922a" ||
    (typeof scen === "string" && scen.toLowerCase().includes("icecube"));

  if (simulated === true) {
    simBadge.hidden = false;
    realBadge.hidden = true;
    return;
  }
  if (simulated === false && isB) {
    realBadge.hidden = false;
    simBadge.hidden = true;
  }
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
    // scenarios.ts also calls requestSkyZoomReplay after onStarted.
  },
});
mountCandidates(document.querySelector("#panel-candidates")!);
mountSubscribe(document.querySelector("#panel-subscribe")!);
mountVoice(document.querySelector("#panel-voice")!);

void hydrateFromLatest();

connectEvents(
  (event) => {
    applyEvent(event);
    if (event.type === "voice") handleVoiceEvent(event);

    if (event.type === "hello") {
      statusEl.textContent = strings.connected;
      const scen = (event as { scenario?: string }).scenario;
      if (scen) activeScenario = scen;
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
    if (state === "open") statusEl.textContent = strings.connected;
    if (state === "closed") statusEl.textContent = strings.disconnected;
  },
);
