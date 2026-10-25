/**
 * BREAKOUT dashboard — Vite + TypeScript.
 * Panels subscribe to /ws/events (proxied to ws://localhost:8000).
 */
import "./style.css";
import strings from "./copy/strings.json";
import { applyBadgeFromEvent, mountBadgeHosts, noteScenario } from "./panels/badges";
import { mountCandidatesPanel } from "./panels/candidates";
import { mountScenariosPanel } from "./panels/scenarios";
import { mountSkyMapPanel } from "./panels/skyMap";
import { applyEvent, setConnected } from "./state/store";
import { connectEvents } from "./ws/events";

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) {
  throw new Error("#app missing");
}

app.innerHTML = `
  <div class="dash">
    <header class="dash-hero">
      <div>
        <p class="brand">${strings.brand}</p>
        <p class="tagline">${strings.tagline}</p>
      </div>
      <div class="hero-status">
        <p class="status" id="status">${strings.connecting}</p>
        <span class="badge simulated" id="sim-badge" hidden>${strings.simulatedBadge}</span>
        <span class="badge real" id="real-badge" hidden>${strings.realBadge}</span>
      </div>
    </header>
    <div class="dash-grid">
      <div id="panel-sky" class="dash-sky"></div>
      <aside class="dash-side">
        <div id="panel-scenarios" class="slot-scenarios"></div>
        <div id="panel-candidates" class="slot-candidates"></div>
      </aside>
    </div>
  </div>
`;

const statusEl = document.querySelector<HTMLElement>("#status")!;
const badges = mountBadgeHosts();

mountSkyMapPanel(document.querySelector("#panel-sky")!);
mountScenariosPanel(document.querySelector("#panel-scenarios")!);
mountCandidatesPanel(document.querySelector("#panel-candidates")!);

// Scenario buttons also note which path was requested (for Real vs Simulated).
document.querySelector("#panel-scenarios")?.addEventListener(
  "click",
  (ev) => {
    const btn = (ev.target as HTMLElement).closest<HTMLButtonElement>("button[data-scenario]");
    if (btn?.dataset.scenario) noteScenario(btn.dataset.scenario);
  },
  true,
);

connectEvents(
  (event) => {
    applyEvent(event);
    applyBadgeFromEvent(badges, event);

    if (event.type === "hello") {
      statusEl.textContent = strings.connected;
    } else if (event.type === "alert") {
      statusEl.textContent = `${strings.statusAlert}: ${String((event.payload as { kind?: string })?.kind ?? "")}`;
    } else if (event.type === "skymap") {
      statusEl.textContent = strings.statusSkymap;
    } else if (event.type === "candidates") {
      statusEl.textContent = strings.statusCandidates;
    } else if (event.type === "scenario_done") {
      statusEl.textContent = `${strings.scenarioStarted}: ${String(event.payload?.scenario ?? "")}`;
    }
  },
  (state) => {
    setConnected(state === "open");
    if (state === "connecting") statusEl.textContent = strings.connecting;
    if (state === "open") statusEl.textContent = strings.connected;
    if (state === "closed") statusEl.textContent = strings.disconnected;
  },
);
