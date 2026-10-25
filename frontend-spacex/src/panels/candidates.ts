/**
 * Ranked object list + detail — same data contract as the mission UI.
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

function fmtDistance(kpc: number | null | undefined): string {
  if (kpc === null || kpc === undefined || Number.isNaN(Number(kpc))) {
    return strings.noData;
  }
  return `${Number(kpc).toFixed(3)} ${strings.distanceUnit}`;
}

function fmtConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return strings.noData;
  }
  return `${(Number(value) * 100).toFixed(0)}%`;
}

function fmtLife(row: CandidateRow): string {
  const life = row.life_expectancy?.optical_breakout_window;
  if (life && !isBreakoutSkipped(life)) return life;
  const bw = row.breakout?.class_window;
  if (bw && !isBreakoutSkipped(bw)) return bw;
  return strings.noData;
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
      <p class="rail-sort">${strings.candidatesSort}</p>
      <p class="rail-hint">${strings.candidatesHint}</p>
      <p class="rail-empty" data-role="empty">${strings.candidatesEmpty}</p>
      <ul class="obj-list" data-role="list" hidden></ul>
      <div class="obj-detail" data-role="detail" hidden>
        <h3 class="obj-detail-name" data-role="detail-name"></h3>
        <div class="obj-attrs" data-role="attrs"></div>
        <p class="detail-reasoning" data-role="reasoning"></p>
        <details class="detail-secondary" data-role="secondary" hidden>
          <summary>${strings.detailEvidence}</summary>
          <ul class="evidence-list" data-role="evidence"></ul>
        </details>
        <ul class="evidence-list" data-role="evidence-primary"></ul>
      </div>
    </div>
  `;

  const empty = host.querySelector<HTMLElement>("[data-role=empty]")!;
  const list = host.querySelector<HTMLElement>("[data-role=list]")!;
  const detail = host.querySelector<HTMLElement>("[data-role=detail]")!;
  const detailName = host.querySelector<HTMLElement>("[data-role=detail-name]")!;
  const attrsEl = host.querySelector<HTMLElement>("[data-role=attrs]")!;
  const reasoningEl = host.querySelector<HTMLElement>("[data-role=reasoning]")!;
  const evidenceEl = host.querySelector<HTMLElement>("[data-role=evidence-primary]")!;
  const secondary = host.querySelector<HTMLDetailsElement>("[data-role=secondary]")!;
  const evidenceSecondary = host.querySelector<HTMLElement>("[data-role=evidence]")!;
  const simBadge = host.querySelector<HTMLElement>("[data-role=sim]")!;

  let tickTimer = 0;
  let detailSeq = 0;
  let detailStarId: string | null = null;
  let lastCandidateKey = "";

  const paintEvidence = (
    target: HTMLElement,
    row: CandidateRow,
    raw: RawLitResponse | null,
  ) => {
    target.innerHTML = "";
    const evidence = row.lit?.evidence?.length
      ? row.lit.evidence
      : raw?.literature?.evidence ?? [];
    if (!evidence.length) {
      const li = document.createElement("li");
      li.textContent = strings.detailNoEvidence;
      target.appendChild(li);
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
      target.appendChild(li);
    }
  };

  const renderAttrs = (row: CandidateRow, now: number) => {
    const conf = fmtConfidence(row.rank_confidence ?? row.lit?.confidence);
    const life = fmtLife(row);
    const composition = row.composition?.trim() || strings.noData;
    const skip = isBreakoutSkipped(row.breakout.class_window);
    const breakout = skip
      ? strings.countdownSkipped
      : `${windowLabel(row.breakout.class_window)} · ${formatElapsed(row.breakout.countdown_from, now)}`;
    const rows: [string, string][] = [
      [strings.colClass, row.class],
      [strings.colDistance, fmtDistance(row.distance_kpc)],
      [strings.colConfidence, conf],
      [strings.colLife, life],
      [strings.colPosterior, row.posterior.toFixed(3)],
      [strings.skyHoverComposition, composition],
      [strings.colBreakout, breakout],
      [
        strings.colIR,
        row.ir_followup ? strings.irYes : strings.irNo,
      ],
    ];
    attrsEl.innerHTML = rows
      .map(
        ([k, v]) => `
      <div class="obj-attr">
        <span class="k">${k}</span>
        <span class="v">${v}</span>
      </div>`,
      )
      .join("");
  };

  const renderDetail = async (row: CandidateRow) => {
    const seq = ++detailSeq;
    const starChanged = detailStarId !== row.star_id;
    detailStarId = row.star_id;
    detail.hidden = false;
    detailName.textContent = row.star_id;
    renderAttrs(row, Date.now());

    const cached = rawCache.has(row.star_id)
      ? (rawCache.get(row.star_id) ?? null)
      : undefined;

    if (starChanged) {
      const inventoryReason = row.rank_reasoning?.trim() || "";
      if (cached === undefined) {
        reasoningEl.textContent = inventoryReason || strings.detailLoading;
        paintEvidence(evidenceEl, row, null);
        secondary.hidden = true;
        evidenceSecondary.innerHTML = "";
      } else if (cached?.reasoning) {
        reasoningEl.textContent = cached.reasoning;
        paintEvidence(evidenceEl, row, cached);
        secondary.hidden = true;
      } else {
        reasoningEl.textContent =
          inventoryReason || cached?.note || strings.detailNoReasoning;
        paintEvidence(evidenceEl, row, cached);
        secondary.hidden = true;
      }
    }

    if (cached !== undefined) return;

    const raw = await fetchRaw(row.star_id);
    if (seq !== detailSeq || detailStarId !== row.star_id) return;

    if (raw?.reasoning) {
      reasoningEl.textContent = raw.reasoning;
    } else {
      reasoningEl.textContent =
        row.rank_reasoning?.trim() ||
        raw?.note ||
        strings.detailNoReasoning;
    }
    paintEvidence(evidenceEl, row, raw);
  };

  const candidateKey = (rows: CandidateRow[]) =>
    rows.map((r) => `${r.star_id}:${r.posterior.toFixed(4)}`).join("|");

  const renderList = (opts: { tickOnly: boolean }) => {
    const { candidates, candidatesSimulated, selectedStarId } = getState();
    simBadge.hidden = !candidatesSimulated;

    if (!candidates.length) {
      list.replaceChildren();
      detailSeq += 1;
      empty.hidden = false;
      list.hidden = true;
      detail.hidden = true;
      detailStarId = null;
      lastCandidateKey = "";
      return;
    }

    empty.hidden = true;
    list.hidden = false;
    const now = Date.now();
    const key = candidateKey(candidates);
    const structureChanged = key !== lastCandidateKey;
    lastCandidateKey = key;

    if (!opts.tickOnly || structureChanged) {
      list.innerHTML = "";
      candidates.forEach((row, i) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "obj-row";
        if (i >= 5) btn.classList.add("is-extended");
        if (row.simulated) btn.classList.add("is-sim");
        btn.setAttribute(
          "aria-pressed",
          row.star_id === selectedStarId ? "true" : "false",
        );
        btn.dataset.starId = row.star_id;
        const conf = row.rank_confidence ?? row.lit?.confidence;
        btn.innerHTML = `
          <span class="obj-rank">${i + 1}</span>
          <span>
            <span class="obj-name">${row.star_id}</span>
            <span class="obj-meta">${row.class} · ${fmtDistance(row.distance_kpc)} · conf ${fmtConfidence(conf)}</span>
          </span>
          <span class="obj-metric" data-role="metric">P ${row.posterior.toFixed(3)}</span>
        `;
        btn.addEventListener("click", () => selectStar(row.star_id));
        li.appendChild(btn);
        list.appendChild(li);
      });
    } else {
      const rows = list.querySelectorAll<HTMLButtonElement>(".obj-row");
      candidates.forEach((row, i) => {
        const btn = rows[i];
        if (!btn) return;
        btn.setAttribute(
          "aria-pressed",
          row.star_id === selectedStarId ? "true" : "false",
        );
        const metric = btn.querySelector<HTMLElement>("[data-role=metric]");
        if (metric && !isBreakoutSkipped(row.breakout.class_window)) {
          metric.title = formatElapsed(row.breakout.countdown_from, now);
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
      detailName.textContent = strings.pickStarHint;
      attrsEl.innerHTML = "";
      reasoningEl.textContent = "";
      evidenceEl.innerHTML = "";
      secondary.hidden = true;
    }
  };

  const unsub = subscribe(() => renderList({ tickOnly: false }));
  tickTimer = window.setInterval(() => renderList({ tickOnly: true }), 1000);

  return () => {
    unsub();
    window.clearInterval(tickTimer);
  };
}
