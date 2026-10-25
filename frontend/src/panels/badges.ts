/**
 * Simulated / Real data badges driven by WebSocket payload flags.
 * Scenario A events are simulated=true; Scenario B is the real-data path.
 */
import strings from "../copy/strings.json";
import type { PipelineEvent } from "../ws/events";

export type BadgeHost = {
  sim: HTMLElement;
  real: HTMLElement;
};

let activeScenario: string | null = null;

export function noteScenario(name: string | null): void {
  activeScenario = name;
}

export function mountBadgeHosts(): BadgeHost {
  const sim = document.querySelector<HTMLElement>("#sim-badge");
  const real = document.querySelector<HTMLElement>("#real-badge");
  if (!sim || !real) {
    throw new Error("badge hosts #sim-badge / #real-badge missing");
  }
  sim.textContent = strings.simulatedBadge;
  real.textContent = strings.realBadge;
  return { sim, real };
}

export function applyBadgeFromEvent(host: BadgeHost, event: PipelineEvent): void {
  if (event.type === "hello") {
    const scen = (event as PipelineEvent & { scenario?: string }).scenario;
    if (scen) activeScenario = scen;
  }
  if (event.type === "scenario_done" && event.payload?.scenario) {
    activeScenario = String(event.payload.scenario);
  }

  const isScenarioB =
    activeScenario === "scenario_b_icecube_170922a" ||
    (typeof event.payload?.alert_id === "string" &&
      String(event.payload.alert_id).toLowerCase().includes("icecube"));

  // Any simulated pipeline payload → Simulated badge (never hide real numbers as real).
  if (event.simulated === true) {
    host.sim.hidden = false;
    host.real.hidden = true;
    return;
  }

  // Explicit real payloads on the Scenario B path.
  if (
    event.simulated === false &&
    (event.type === "alert" || event.type === "skymap" || event.type === "candidates") &&
    isScenarioB
  ) {
    host.real.hidden = false;
    host.sim.hidden = true;
    return;
  }
}
