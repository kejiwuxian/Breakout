/**
 * Sky map panel: Mollweide PNG from FastAPI + candidate markers.
 * Uses an <img> + SVG overlay (no WebGL required for the map itself).
 */
import strings from "../copy/strings.json";
import { getState, subscribe, type CandidateRow, type SkymapPayload } from "../state/store";
import { raDecToMollweide } from "../sky/mollweide";

function skymapPngUrl(alertId: string): string {
  return `/api/skymap/${encodeURIComponent(alertId)}/png`;
}

export function mountSkyMapPanel(host: HTMLElement): () => void {
  host.innerHTML = `
    <section class="panel sky-panel" aria-labelledby="sky-title">
      <header class="panel-head">
        <h2 id="sky-title">${strings.skyTitle}</h2>
        <span class="badge simulated" data-role="sim" hidden>${strings.simulatedBadge}</span>
      </header>
      <p class="panel-empty" data-role="empty">${strings.skyEmpty}</p>
      <div class="sky-stage" data-role="stage" hidden>
        <img class="sky-img" data-role="img" alt="${strings.skyTitle}" />
        <svg class="sky-overlay" data-role="overlay" aria-hidden="true"></svg>
        <p class="sky-meta" data-role="meta"></p>
      </div>
    </section>
  `;

  const empty = host.querySelector<HTMLElement>("[data-role=empty]")!;
  const stage = host.querySelector<HTMLElement>("[data-role=stage]")!;
  const img = host.querySelector<HTMLImageElement>("[data-role=img]")!;
  const overlay = host.querySelector<SVGSVGElement>("[data-role=overlay]")!;
  const meta = host.querySelector<HTMLElement>("[data-role=meta]")!;
  const simBadge = host.querySelector<HTMLElement>("[data-role=sim]")!;

  let lastAlertId: string | null = null;

  const drawMarkers = (skymap: SkymapPayload, candidates: CandidateRow[]) => {
    const w = img.clientWidth || stage.clientWidth || 640;
    const h = img.clientHeight || Math.round(w * 0.5);
    overlay.setAttribute("viewBox", `0 0 ${w} ${h}`);
    overlay.setAttribute("width", String(w));
    overlay.setAttribute("height", String(h));
    overlay.innerHTML = "";

    const peak = raDecToMollweide(skymap.peak.ra_deg, skymap.peak.dec_deg, w, h);
    if (peak) {
      const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("cx", String(peak.x));
      c.setAttribute("cy", String(peak.y));
      c.setAttribute("r", "5");
      c.setAttribute("class", "marker peak");
      overlay.appendChild(c);
    }

    for (const row of candidates) {
      const pt = raDecToMollweide(row.ra_deg, row.dec_deg, w, h);
      if (!pt) continue;
      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", "marker candidate");
      const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("cx", String(pt.x));
      c.setAttribute("cy", String(pt.y));
      c.setAttribute("r", "4");
      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = `${row.star_id} · ${row.class}`;
      g.appendChild(title);
      g.appendChild(c);
      overlay.appendChild(g);
    }
  };

  const render = () => {
    const { skymap, candidates } = getState();
    if (!skymap) {
      empty.hidden = false;
      stage.hidden = true;
      simBadge.hidden = true;
      return;
    }

    empty.hidden = true;
    stage.hidden = false;
    simBadge.hidden = !skymap.simulated;
    meta.textContent = `${strings.skyPeak}: RA ${skymap.peak.ra_deg.toFixed(3)}°  Dec ${skymap.peak.dec_deg.toFixed(3)}° · ${skymap.credible_90_deg2.toFixed(1)} deg² (90%)`;

    if (skymap.alert_id !== lastAlertId) {
      lastAlertId = skymap.alert_id;
      img.alt = `${strings.skyTitle} ${skymap.alert_id}`;
      img.onload = () => drawMarkers(skymap, candidates);
      img.onerror = () => {
        empty.hidden = false;
        empty.textContent = strings.skyError;
        stage.hidden = true;
      };
      img.src = skymapPngUrl(skymap.alert_id);
    } else if (img.complete && img.naturalWidth > 0) {
      drawMarkers(skymap, candidates);
    }
  };

  const unsub = subscribe(render);
  const onResize = () => {
    const { skymap, candidates } = getState();
    if (skymap && img.complete) drawMarkers(skymap, candidates);
  };
  window.addEventListener("resize", onResize);

  return () => {
    unsub();
    window.removeEventListener("resize", onResize);
  };
}
