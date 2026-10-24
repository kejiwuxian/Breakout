/**
 * BREAKOUT dashboard scaffold (Vite + TypeScript + Three.js).
 * Sky map, panels, and WebSocket wiring are filled in later prompts.
 */
import "./style.css";
import strings from "./copy/strings.json";
import { mountSkyPlaceholder } from "./sky/scene";
import { connectAnnouncer } from "./voice/announcer";

const app = document.querySelector<HTMLDivElement>("#app");
if (app) {
  app.innerHTML = `
    <main class="shell">
      <p class="brand">${strings.brand}</p>
      <p class="tagline">${strings.tagline}</p>
      <div class="sky" id="sky" aria-label="Sky map placeholder"></div>
      <p class="status" id="status">${strings.connecting}</p>
      <span class="badge simulated" hidden id="sim-badge">${strings.simulatedBadge}</span>
    </main>
  `;
  const sky = document.querySelector<HTMLElement>("#sky");
  if (sky) mountSkyPlaceholder(sky);
}

connectAnnouncer();

