/**
 * Dominant skymap plane — Mollweide PNG from Light's fuse output.
 */
import strings from "../copy/strings.json";
import { getState, subscribe } from "../state/store";

export function mountSky(host: HTMLElement): () => void {
  host.innerHTML = `
    <div class="sky-stage" data-role="stage">
      <div class="sky-empty" data-role="empty">${strings.skyEmpty}</div>
      <img class="sky-img" data-role="img" alt="${strings.skyTitle}" hidden />
      <div class="sky-meta" data-role="meta" hidden></div>
    </div>
  `;

  const empty = host.querySelector<HTMLElement>("[data-role=empty]")!;
  const img = host.querySelector<HTMLImageElement>("[data-role=img]")!;
  const meta = host.querySelector<HTMLElement>("[data-role=meta]")!;

  const render = () => {
    const { skymap } = getState();
    if (!skymap) {
      empty.hidden = false;
      img.hidden = true;
      meta.hidden = true;
      return;
    }
    empty.hidden = true;
    img.hidden = false;
    meta.hidden = false;
    const src = `/api/skymap/${encodeURIComponent(skymap.alert_id)}/png`;
    if (img.getAttribute("src") !== src) {
      img.alt = `${strings.skyTitle} ${skymap.alert_id}`;
      img.src = src;
      img.classList.remove("is-in");
      img.addEventListener(
        "load",
        () => img.classList.add("is-in"),
        { once: true },
      );
    }
    const peak = skymap.peak;
    meta.innerHTML = `
      <span>${strings.skyPeak} RA ${peak.ra_deg.toFixed(2)}° · Dec ${peak.dec_deg.toFixed(2)}°</span>
      <span>90% · ${skymap.credible_90_deg2.toFixed(1)} deg²</span>
      ${skymap.simulated ? `<span class="badge sim">${strings.simulatedBadge}</span>` : `<span class="badge real">${strings.realBadge}</span>`}
    `;
  };

  return subscribe(render);
}
