/**
 * Scenario replay controls — same POST /scenario/{id}/start as classic UI.
 */
import strings from "../copy/strings.json";
import { requestSkyZoomReplay } from "../state/store";

const SCENARIOS: { id: string; label: string; realData: boolean }[] = [
  {
    id: "scenario_a_galactic_ccsn",
    label: strings.scenarioA,
    realData: false,
  },
  {
    id: "scenario_b_icecube_170922a",
    label: strings.scenarioB,
    realData: true,
  },
];

export function mountScenarios(
  host: HTMLElement,
  onScenario?: (id: string) => void,
): () => void {
  host.innerHTML = `
    <div class="rail-block scenarios">
      <h2 class="rail-title">${strings.scenariosTitle}</h2>
      <div class="scenario-list" data-role="list"></div>
      <p class="scenario-status" data-role="status" aria-live="polite"></p>
    </div>
  `;

  const list = host.querySelector<HTMLElement>("[data-role=list]")!;
  const status = host.querySelector<HTMLElement>("[data-role=status]")!;

  for (const scen of SCENARIOS) {
    const row = document.createElement("div");
    row.className = "scenario-row";
    const label = document.createElement("div");
    label.className = "scenario-label";
    label.innerHTML = `
      <span class="scenario-name">${scen.label}</span>
      <span class="badge ${scen.realData ? "real" : "sim"}">${
        scen.realData ? strings.realBadge : strings.simulatedBadge
      }</span>
    `;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "scenario-btn";
    btn.textContent = strings.scenarioStart;
    btn.dataset.scenario = scen.id;
    btn.addEventListener("click", async () => {
      onScenario?.(scen.id);
      requestSkyZoomReplay();
      btn.disabled = true;
      btn.textContent = strings.scenarioStarting;
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
      } catch (err) {
        status.textContent = `${strings.scenarioFailed}: ${String(err)}`;
      } finally {
        btn.disabled = false;
        btn.textContent = strings.scenarioStart;
      }
    });
    row.appendChild(label);
    row.appendChild(btn);
    list.appendChild(row);
  }

  return () => {
    list.innerHTML = "";
  };
}
