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

function fmtConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return strings.distanceUnknown;
  }
  return `${(Number(value) * 100).toFixed(0)}%`;
}

function fmtLife(row: CandidateRow): string {
  const life = row.life_expectancy?.optical_breakout_window;
  if (life) return life;
  return row.breakout?.class_window || strings.distanceUnknown;
}

type RawLitResponse = {
  reasoning?: string | null;
  literature?: { evidence?: { bibcode: string; claim: string }[] };
  note?: string;
  raw_missing?: boolean;
};

const rawCache = new Map<string, RawLitResponse | null>();
const rawInflight = new Map<string, Promise<RawLitResponse | null>>();

async function fetchRaw(starId: string): Promise<RawLitResponse | null> {
  if (rawCache.has(starId)) return rawCache.get(starId) ?? null;
  const pending = rawInflight.get(starId);
  if (pending) return pending;

  const req = (async () => {
    try {
      const res = await fetch(
        `/api/literature/raw/${encodeURIComponent(starId)}`,
      );
      if (!res.ok) {
        rawCache.set(starId, null);
        return null;
      }
      const body = (await res.json()) as RawLitResponse;
      rawCache.set(starId, body);
      return body;
    } catch {
      rawCache.set(starId, null);
      return null;
    } finally {
      rawInflight.delete(starId);
    }
  })();

  rawInflight.set(starId, req);
  return req;
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
              <th>${strings.colDistance}</th>
              <th>${strings.colConfidence}</th>
              <th>${strings.colLife}</th>
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
  let detailStarId: string | null = null;
  let lastCandidateKey = "";

  const paintEvidence = (
    row: CandidateRow,
    raw: RawLitResponse | null,
  ) => {
    evidenceEl.innerHTML = "";
    const evidence = row.lit?.evidence?.length
      ? row.lit.evidence
      : raw?.literature?.evidence ?? [];
    if (!evidence.length) {
      const li = document.createElement("li");
      li.textContent = strings.detailNoEvidence;
      evidenceEl.appendChild(li);
      return;
    }
    for (const ev of evidence) {
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

  const renderDetail = async (row: CandidateRow) => {
    const seq = ++detailSeq;
    const starChanged = detailStarId !== row.star_id;
    detailStarId = row.star_id;
    detail.hidden = false;
    const conf = fmtConfidence(row.rank_confidence ?? row.lit?.confidence);
    const life = fmtLife(row);
    detailStar.textContent = `${row.star_id} · ${row.class} · ${fmtDistance(row.distance_kpc)} · ${strings.colConfidence} ${conf} · ${strings.colLife} ${life}`;

    const cached = rawCache.has(row.star_id)
      ? (rawCache.get(row.star_id) ?? null)
      : undefined;

    if (starChanged) {
      // Only clear/replace when the selected star changes — never on countdown ticks.
      const inventoryReason = row.rank_reasoning?.trim() || "";
      if (cached === undefined) {
        reasoningEl.textContent = inventoryReason || strings.detailLoading;
        evidenceEl.innerHTML = "";
        // Show row evidence immediately while raw reasoning loads.
        paintEvidence(row, null);
      } else if (cached?.reasoning) {
        reasoningEl.textContent = cached.reasoning;
        paintEvidence(row, cached);
      } else {
        reasoningEl.textContent =
          inventoryReason || cached?.note || strings.detailNoReasoning;
        paintEvidence(row, cached);
      }
    }

    if (cached !== undefined) return;

    const raw = await fetchRaw(row.star_id);
    if (seq !== detailSeq || detailStarId !== row.star_id) return;

    if (raw?.reasoning) {
      reasoningEl.textContent = raw.reasoning;
    } else {
      reasoningEl.textContent = raw?.note || strings.detailNoReasoning;
    }
    paintEvidence(row, raw);
  };

  const candidateKey = (rows: CandidateRow[]) =>
    rows.map((r) => `${r.star_id}:${r.posterior.toFixed(4)}`).join("|");

  const renderTable = (opts: { tickOnly: boolean }) => {
    const { candidates, candidatesSimulated, selectedStarId } = getState();
    simBadge.hidden = !candidatesSimulated;

    if (!candidates.length) {
      empty.hidden = false;
      wrap.hidden = true;
      detail.hidden = true;
      detailStarId = null;
      lastCandidateKey = "";
      return;
    }

    empty.hidden = true;
    wrap.hidden = false;
    const now = Date.now();
    const key = candidateKey(candidates);
    const structureChanged = key !== lastCandidateKey;
    lastCandidateKey = key;

    if (!opts.tickOnly || structureChanged) {
      tbody.innerHTML = "";
      candidates.forEach((row, i) => {
        const tr = document.createElement("tr");
        if (row.star_id === selectedStarId) tr.classList.add("selected");
        if (row.simulated) tr.classList.add("is-sim");
        tr.tabIndex = 0;
        const skip = isBreakoutSkipped(row.breakout.class_window);
        const conf = row.rank_confidence ?? row.lit?.confidence;
        tr.innerHTML = `
          <td>${i + 1}</td>
          <td class="star-id">${escapeHtml(row.star_id)}</td>
          <td>${escapeHtml(row.class)}</td>
          <td class="mono">${escapeHtml(fmtDistance(row.distance_kpc))}</td>
          <td class="mono" title="${escapeHtml(row.rank_reasoning || "")}">${escapeHtml(fmtConfidence(conf))}</td>
          <td class="mono" title="${escapeHtml(row.life_expectancy?.basis || "")}">${escapeHtml(fmtLife(row))}</td>
          <td class="mono">${row.posterior.toFixed(3)}</td>
          <td class="breakout" title="${skip ? strings.countdownSkipped : strings.countdownEstimate}">
            <span class="bw">${escapeHtml(windowLabel(row.breakout.class_window))}</span>
            ${
              skip
                ? ""
                : `<span class="elapsed" data-role="elapsed">${formatElapsed(row.breakout.countdown_from, now)}</span>`
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
    } else {
      // Countdown tick: update elapsed labels + selection highlight only.
      const rows = tbody.querySelectorAll("tr");
      candidates.forEach((row, i) => {
        const tr = rows[i];
        if (!tr) return;
        tr.classList.toggle("selected", row.star_id === selectedStarId);
        const elapsed = tr.querySelector<HTMLElement>("[data-role=elapsed]");
        if (elapsed && !isBreakoutSkipped(row.breakout.class_window)) {
          elapsed.textContent = formatElapsed(row.breakout.countdown_from, now);
        }
      });
    }

    const selected = selectedStarId
      ? candidates.find((c) => c.star_id === selectedStarId)
      : undefined;
    if (selected) {
      detail.hidden = false;
      void renderDetail(selected);
    } else {
      detail.hidden = false;
      detailStarId = null;
      detailStar.textContent = strings.pickStarHint ?? "Hover or click a star to inspect.";
      reasoningEl.textContent = "";
      evidenceEl.innerHTML = "";
    }
  };

  const unsub = subscribe(() => renderTable({ tickOnly: false }));
  tickTimer = window.setInterval(() => renderTable({ tickOnly: true }), 1000);

  return () => {
    unsub();
    window.clearInterval(tickTimer);
  };
}
