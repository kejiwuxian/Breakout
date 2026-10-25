/**
 * BREAKOUT frontend-v2 — redesigned mission UI.
 * Same backend contracts as frontend/; does not replace the classic dashboard.
 */
import "./style.css";
import strings from "./copy/strings.json";
import { mountCandidates } from "./panels/candidates";
import { mountScenarios } from "./panels/scenarios";
import { mountSky } from "./panels/sky";
import { handleVoiceEvent, mountVoice } from "./panels/voice";
import { applyEvent, setConnected } from "./state/store";
import { connectEvents } from "./ws/events";

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
mountScenarios(document.querySelector("#panel-scenarios")!, (id) => {
  activeScenario = id;
});
mountCandidates(document.querySelector("#panel-candidates")!);
mountVoice(document.querySelector("#panel-voice")!);

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
