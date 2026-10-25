/**
 * Dashboard state fed by /ws/events — same contract as frontend/.
 */
import type { PipelineEvent } from "../ws/events";

export type LifeExpectancyRow = {
  optical_breakout_window: string;
  stellar_stage_note?: string | null;
  confidence: number;
  basis: string;
};

export type CandidateRow = {
  star_id: string;
  ra_deg: number;
  dec_deg: number;
  class: string;
  spectral_type: string;
  distance_kpc: number | null;
  extinction_av_mag: number | null;
  p_sky: number;
  vmag?: number | null;
  lit: {
    mass_loss: number;
    variability: number;
    evolved_stage: number;
    confidence: number;
    evidence: { bibcode: string; claim: string }[];
  };
  presn_watch: boolean;
  posterior: number;
  breakout: { class_window: string; countdown_from: string };
  ir_followup: boolean;
  simulated: boolean;
  /** v1.1 optional inventory / Grok rank fields */
  rank_confidence?: number | null;
  rank_reasoning?: string | null;
  life_expectancy?: LifeExpectancyRow | null;
  composition?: string | null;
};

export type SkymapPayload = {
  alert_id: string;
  nside: number;
  ordering: string;
  frame: string;
  prob_path: string;
  components: string[];
  credible_90_deg2: number;
  peak: { ra_deg: number; dec_deg: number };
  simulated: boolean;
};

export type DashState = {
  connected: boolean;
  scenario: string | null;
  lastSimulated: boolean | null;
  alert: Record<string, unknown> | null;
  skymap: SkymapPayload | null;
  candidates: CandidateRow[];
  candidatesSimulated: boolean;
  selectedStarId: string | null;
  voiceCaption: string;
  voiceSimulated: boolean;
  /** When true, next skymap render shows full sky without replaying zoom. */
  suppressSkyZoomOnce: boolean;
  /** Bumped on Scenario Run so zoom replays even if alert_id is reused. */
  skyZoomNonce: number;
  /**
   * Monotonic epoch bumped when the user starts a new scenario. Sky/hydrate
   * paths ignore stale payloads from a previous epoch (overlapping WS +
   * /alerts/latest races).
   */
  missionEpoch: number;
};

type Listener = (state: DashState) => void;

const state: DashState = {
  connected: false,
  scenario: null,
  lastSimulated: null,
  alert: null,
  skymap: null,
  candidates: [],
  candidatesSimulated: false,
  selectedStarId: null,
  voiceCaption: "",
  voiceSimulated: false,
  suppressSkyZoomOnce: false,
  skyZoomNonce: 0,
  missionEpoch: 0,
};

const listeners = new Set<Listener>();

export function getState(): DashState {
  return state;
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  listener(state);
  return () => listeners.delete(listener);
}

function emit(): void {
  for (const listener of listeners) listener(state);
}

export function setConnected(connected: boolean): void {
  state.connected = connected;
  emit();
}

export function selectStar(starId: string | null): void {
  state.selectedStarId = starId;
  emit();
}

export function setVoiceCaption(text: string, simulated: boolean): void {
  state.voiceCaption = text;
  state.voiceSimulated = simulated;
  emit();
}

/**
 * Drop the previous mission sky/candidates immediately when the user picks a
 * new scenario so the map cannot zoom into the prior AOI while the next
 * package is still in flight.
 */
export function beginScenarioSwitch(scenarioId: string): number {
  state.scenario = scenarioId;
  state.alert = null;
  state.skymap = null;
  state.candidates = [];
  state.candidatesSimulated = false;
  state.selectedStarId = null;
  state.lastSimulated = null;
  state.voiceCaption = "";
  state.suppressSkyZoomOnce = false;
  state.skyZoomNonce += 1;
  state.missionEpoch += 1;
  emit();
  return state.missionEpoch;
}

/** Seed skymap + candidates without a live WS event (e.g. /alerts/latest hydrate). */
export function hydrateMission(opts: {
  skymap: SkymapPayload;
  candidates?: CandidateRow[];
  simulated?: boolean;
  /**
   * When true (default), next sky render stays full-sky (page-load hydrate).
   * Pass false after Scenario Run so AOI zoom can play on the fresh package.
   */
  suppressZoom?: boolean;
  /** Reject stale hydrates from a previous scenario switch. */
  expectEpoch?: number;
}): boolean {
  if (
    typeof opts.expectEpoch === "number" &&
    opts.expectEpoch !== state.missionEpoch
  ) {
    return false;
  }
  state.skymap = opts.skymap;
  state.suppressSkyZoomOnce = opts.suppressZoom !== false;
  if (opts.candidates) {
    state.candidates = [...opts.candidates].sort(
      (a, b) => b.posterior - a.posterior,
    );
    if (typeof opts.simulated === "boolean") {
      state.candidatesSimulated = opts.simulated;
    }
    // Do not auto-select (e.g. Betelgeuse) — wait for user hover/click.
  }
  if (typeof opts.simulated === "boolean") {
    state.lastSimulated = opts.simulated;
  }
  emit();
  return true;
}

/** Call when the user starts a scenario so the sky zoom sequence can replay. */
export function requestSkyZoomReplay(): void {
  state.suppressSkyZoomOnce = false;
  state.skyZoomNonce += 1;
  emit();
}

export function clearSkyZoomSuppress(): void {
  if (!state.suppressSkyZoomOnce) return;
  state.suppressSkyZoomOnce = false;
}

/**
 * True when a community /alerts package belongs to the given scenario id.
 * Prevents hydrating the previous run's package while the new scenario is still writing.
 */
export function packageMatchesScenario(
  pkg: { alert_id?: string; simulated?: boolean },
  scenarioId: string,
): boolean {
  const id = String(pkg.alert_id ?? "");
  if (scenarioId === "scenario_b_icecube_170922a") {
    return /icecube/i.test(id);
  }
  if (scenarioId === "scenario_a_galactic_ccsn") {
    return Boolean(pkg.simulated) || /^sim[-_]/i.test(id);
  }
  return Boolean(id);
}

/**
 * After beginScenarioSwitch, the previous scenario's pipeline may still emit
 * WS frames. Drop those so we never paint/zoom the wrong AOI or flip badges.
 */
function isStaleScenarioEvent(event: PipelineEvent): boolean {
  const scen = state.scenario;
  if (!scen) return false;

  if (event.type === "skymap" && event.payload) {
    const next = event.payload as SkymapPayload;
    return !packageMatchesScenario(
      {
        alert_id: next.alert_id,
        simulated:
          typeof event.simulated === "boolean"
            ? event.simulated
            : next.simulated,
      },
      scen,
    );
  }

  if (
    event.type === "alert" ||
    event.type === "candidates" ||
    event.type === "voice"
  ) {
    if (scen === "scenario_b_icecube_170922a") {
      // IceCube replay is historical (simulated=false).
      return event.simulated === true;
    }
    if (scen === "scenario_a_galactic_ccsn") {
      return event.simulated === false;
    }
  }

  if (event.type === "scenario_done" && event.payload?.scenario) {
    return String(event.payload.scenario) !== scen;
  }

  return false;
}

export function applyEvent(event: PipelineEvent): void {
  if (event.type === "hello") {
    const flat = event as PipelineEvent & { scenario?: string };
    const scenario = flat.scenario ?? (event.payload?.scenario as string | undefined);
    // Do not let a reconnect hello roll back a user-selected scenario switch.
    if (typeof scenario === "string" && scenario !== "live_waiting") {
      if (!state.scenario || state.scenario === scenario) {
        state.scenario = scenario;
      }
    } else if (scenario === "live_waiting" && !state.scenario) {
      state.scenario = null;
    }
    emit();
    return;
  }

  if (isStaleScenarioEvent(event)) {
    return;
  }

  if (typeof event.simulated === "boolean") {
    state.lastSimulated = event.simulated;
  }

  if (event.type === "alert" && event.payload) {
    state.alert = event.payload;
  }

  if (event.type === "skymap" && event.payload) {
    state.skymap = event.payload as SkymapPayload;
  }

  if (event.type === "candidates" && event.payload) {
    const list = (event.payload.candidates as CandidateRow[]) || [];
    state.candidates = [...list].sort((a, b) => b.posterior - a.posterior);
    state.candidatesSimulated = Boolean(event.simulated);
    // Keep selection null until the user picks a star on the map or table.
  }

  if (event.type === "voice" && event.payload) {
    const text = String((event.payload as { text?: string }).text ?? "");
    if (text) {
      state.voiceCaption = text;
      state.voiceSimulated = Boolean(event.simulated);
    }
  }

  if (event.type === "scenario_done" && event.payload?.scenario) {
    state.scenario = String(event.payload.scenario);
  }

  emit();
}
