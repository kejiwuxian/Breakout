/**
 * Ranked candidates + ADS evidence — same data contract as classic UI.
 */
import strings from "../copy/strings.json";
import {
  getState,
  selectStar,
  subscribe,
  type CandidateRow,
} from "../state/store";
import { adsUrl } from "../util/ads";
import {
  formatElapsed,
  isBreakoutSkipped,
  windowLabel,
} from "../util/countdown";

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fmtDistance(kpc: number | null | undefined): string {
  if (kpc === null || kpc === undefined || Number.isNaN(Number(kpc))) {
    return strings.distanceUnknown;
  }
  return `${Number(kpc).toFixed(3)} ${strings.distanceUnit}`;
}

async function fetchRaw(starId: string): Promise<{
  reasoning?: string | null;
  literature?: { evidence?: { bibcode: string; claim: string }[] };
  note?: string;
} | null> {
  try {
    const res = await fetch(`/api/literature/raw/${encodeURIComponent(starId)}`);
    if (!res.ok) return null;
    return (await res.json()) as {
      reasoning?: string | null;
      literature?: { evidence?: { bibcode: string; claim: string }[] };
      note?: string;
    };
  } catch {
    return null;
  }
}

export function mountCandidates(host: HTMLElement): () => void {
  host.innerHTML = `
    <div class="rail-block candidates">
      <div class="rail-head">
        <h2 class="rail-title">${strings.candidatesTitle}</h2>
        <span class="badge sim" data-role="sim" hidden>${strings.simulatedBadge}</span>
      </div>
      <p class="rail-hint">${strings.candidatesHint}</p>
      <p class="rail-empty" data-role="empty">${strings.candidatesEmpty}</p>
      <div class="cand-wrap" data-role="table-wrap" hidden>
        <table class="cand-table">
          <thead>
            <tr>
              <th>${strings.colRank}</th>
              <th>${strings.colStar}</th>
              <th>${strings.colClass}</th>
              <th>${strings.colPosterior}</th>
              <th>${strings.colBreakout}</th>
            </tr>
          </thead>
          <tbody data-role="tbody"></tbody>
        </table>
      </div>
      <div class="cand-detail" data-role="detail" hidden>
        <h3>${strings.detailTitle}</h3>
        <p class="detail-star" data-role="detail-star"></p>
        <p class="detail-reasoning" data-role="reasoning"></p>
        <ul class="evidence-list" data-role="evidence"></ul>
      </div>
    </div>
  `;

  const empty = host.querySelector<HTMLElement>("[data-role=empty]")!;
  const wrap = host.querySelector<HTMLElement>("[data-role=table-wrap]")!;
  const tbody = host.querySelector<HTMLElement>("[data-role=tbody]")!;
  const detail = host.querySelector<HTMLElement>("[data-role=detail]")!;
  const detailStar = host.querySelector<HTMLElement>("[data-role=detail-star]")!;
  const reasoningEl = host.querySelector<HTMLElement>("[data-role=reasoning]")!;
  const evidenceEl = host.querySelector<HTMLElement>("[data-role=evidence]")!;
  const simBadge = host.querySelector<HTMLElement>("[data-role=sim]")!;

  let tickTimer = 0;
  let detailSeq = 0;

  const renderDetail = async (row: CandidateRow) => {
    const seq = ++detailSeq;
    detail.hidden = false;
    detailStar.textContent = `${row.star_id} · ${row.class} · ${fmtDistance(row.distance_kpc)}`;
    reasoningEl.textContent = strings.detailNoReasoning;
    evidenceEl.innerHTML = "";

    const evidence = row.lit?.evidence ?? [];
    const raw = await fetchRaw(row.star_id);
    if (seq !== detailSeq) return;

    if (raw?.reasoning) {
      reasoningEl.textContent = raw.reasoning;
    } else {
      reasoningEl.textContent = raw?.note || strings.detailNoReasoning;
    }

    const merged = evidence.length ? evidence : raw?.literature?.evidence ?? [];
    if (!merged.length) {
      const li = document.createElement("li");
      li.textContent = strings.detailNoEvidence;
      evidenceEl.appendChild(li);
      return;
    }
    for (const ev of merged) {
      if (!ev.bibcode || !ev.claim) continue;
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = adsUrl(ev.bibcode);
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = `${strings.adsLinkLabel} ${ev.bibcode}`;
      const claim = document.createElement("span");
      claim.textContent = ` — ${ev.claim}`;
      li.appendChild(a);
      li.appendChild(claim);
      evidenceEl.appendChild(li);
    }
  };

  const renderTable = () => {
    const { candidates, candidatesSimulated, selectedStarId } = getState();
    simBadge.hidden = !candidatesSimulated;

    if (!candidates.length) {
      empty.hidden = false;
      wrap.hidden = true;
      detail.hidden = true;
      return;
    }

    empty.hidden = true;
    wrap.hidden = false;
    const now = Date.now();
    tbody.innerHTML = "";

    candidates.forEach((row, i) => {
      const tr = document.createElement("tr");
      if (row.star_id === selectedStarId) tr.classList.add("selected");
      if (row.simulated) tr.classList.add("is-sim");
      tr.tabIndex = 0;
      const skip = isBreakoutSkipped(row.breakout.class_window);
      tr.innerHTML = `
        <td>${i + 1}</td>
        <td class="star-id">${escapeHtml(row.star_id)}</td>
        <td>${escapeHtml(row.class)}</td>
        <td class="mono">${row.posterior.toFixed(3)}</td>
        <td class="breakout" title="${skip ? strings.countdownSkipped : strings.countdownEstimate}">
          <span class="bw">${escapeHtml(windowLabel(row.breakout.class_window))}</span>
          ${
            skip
              ? ""
              : `<span class="elapsed">${formatElapsed(row.breakout.countdown_from, now)}</span>`
          }
        </td>
      `;
      tr.addEventListener("click", () => selectStar(row.star_id));
      tr.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          selectStar(row.star_id);
        }
      });
      tbody.appendChild(tr);
    });

    const selected =
      candidates.find((c) => c.star_id === selectedStarId) ?? candidates[0]!;
    void renderDetail(selected);
  };

  const unsub = subscribe(renderTable);
  tickTimer = window.setInterval(renderTable, 1000);

  return () => {
    unsub();
    window.clearInterval(tickTimer);
  };
}
