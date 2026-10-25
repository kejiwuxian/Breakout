/**
 * Scenario start buttons → POST /scenario/{name}/start
 */
import strings from "../copy/strings.json";

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

export function mountScenariosPanel(host: HTMLElement): () => void {
  host.innerHTML = `
    <section class="panel scenarios-panel" aria-labelledby="scen-title">
      <header class="panel-head">
        <h2 id="scen-title">${strings.scenariosTitle}</h2>
      </header>
      <div class="scenario-list" data-role="list"></div>
      <p class="scenario-status" data-role="status" aria-live="polite"></p>
    </section>
  `;

  const list = host.querySelector<HTMLElement>("[data-role=list]")!;
  const status = host.querySelector<HTMLElement>("[data-role=status]")!;

  for (const scen of SCENARIOS) {
    const row = document.createElement("div");
    row.className = "scenario-row";
    const label = document.createElement("span");
    label.className = "scenario-label";
    label.textContent = scen.label;
    if (scen.realData) {
      const badge = document.createElement("span");
      badge.className = "badge real";
      badge.textContent = strings.realBadge;
      label.appendChild(document.createTextNode(" "));
      label.appendChild(badge);
    } else {
      const badge = document.createElement("span");
      badge.className = "badge simulated";
      badge.textContent = strings.simulatedBadge;
      label.appendChild(document.createTextNode(" "));
      label.appendChild(badge);
    }
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "scenario-btn";
    btn.textContent = strings.scenarioStart;
    btn.dataset.scenario = scen.id;
    btn.addEventListener("click", async () => {
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
