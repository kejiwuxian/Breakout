/**
 * Event select cards — same POST /scenario/{id}/start as the mission UI.
 */
import strings from "../copy/strings.json";

export type ScenarioHooks = {
  onScenario?: (id: string) => void;
  /** Re-pull /alerts/latest after a successful start (covers WS-offline demos). */
  onStarted?: (id: string) => void | Promise<void>;
};

const SCENARIOS: {
  id: string;
  label: string;
  desc: string;
  icon: string;
  realData: boolean;
}[] = [
  {
    id: "scenario_a_galactic_ccsn",
    label: strings.scenarioA,
    desc: strings.scenarioADesc,
    icon: "A",
    realData: false,
  },
  {
    id: "scenario_b_icecube_170922a",
    label: strings.scenarioB,
    desc: strings.scenarioBDesc,
    icon: "B",
    realData: true,
  },
];

export function mountScenarios(
  host: HTMLElement,
  onScenario?: ((id: string) => void) | ScenarioHooks,
): () => void {
  const hooks: ScenarioHooks =
    typeof onScenario === "function" ? { onScenario } : onScenario ?? {};
  host.innerHTML = `
    <div class="event-select">
      <div class="scenario-list" data-role="list" role="group" aria-label="${strings.scenariosTitle}"></div>
      <p class="scenario-status" data-role="status" aria-live="polite"></p>
    </div>
  `;

  const list = host.querySelector<HTMLElement>("[data-role=list]")!;
  const status = host.querySelector<HTMLElement>("[data-role=status]")!;
  const cards = new Map<string, HTMLButtonElement>();

  const setPressed = (id: string | null) => {
    for (const [sid, btn] of cards) {
      btn.setAttribute("aria-pressed", sid === id ? "true" : "false");
    }
  };

  for (const scen of SCENARIOS) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "event-card";
    btn.dataset.scenario = scen.id;
    btn.setAttribute("aria-pressed", "false");
    btn.innerHTML = `
      <div class="event-card-top">
        <span class="event-card-icon" aria-hidden="true">${scen.icon}</span>
        <span class="badge ${scen.realData ? "hist" : "sim"}">${
          scen.realData ? strings.realBadge : strings.simulatedBadge
        }</span>
      </div>
      <p class="event-card-name">${scen.label}</p>
      <p class="event-card-desc">${scen.desc}</p>
      <span class="event-card-run" data-role="run-label">${strings.scenarioStart}</span>
    `;
    const runLabel = btn.querySelector<HTMLElement>("[data-role=run-label]")!;
    btn.addEventListener("click", async () => {
      hooks.onScenario?.(scen.id);
      setPressed(scen.id);
      btn.disabled = true;
      runLabel.textContent = strings.scenarioStarting;
      status.textContent = "";
      try {
        const res = await fetch(
          `/scenario/${encodeURIComponent(scen.id)}/start?speed=0`,
          { method: "POST" },
        );
        if (!res.ok) {
          const body = await res.text();
          throw new Error(body || String(res.status));
        }
        status.textContent = `${strings.scenarioStarted}: ${scen.id}`;
        // Zoom is triggered once by main (WS skymap or filtered hydrate) —
        // do not bump skyZoomNonce here (that caused a double zoom flash).
        await hooks.onStarted?.(scen.id);
      } catch (err) {
        status.textContent = `${strings.scenarioFailed}: ${String(err)}`;
        btn.setAttribute("aria-pressed", "false");
      } finally {
        btn.disabled = false;
        runLabel.textContent = strings.scenarioStart;
      }
    });
    cards.set(scen.id, btn);
    list.appendChild(btn);
  }

  return () => {
    list.innerHTML = "";
  };
}
