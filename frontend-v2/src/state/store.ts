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
}): void {
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

export function applyEvent(event: PipelineEvent): void {
  if (typeof event.simulated === "boolean") {
    state.lastSimulated = event.simulated;
  }

  if (event.type === "hello") {
    const flat = event as PipelineEvent & { scenario?: string };
    const scenario = flat.scenario ?? (event.payload?.scenario as string | undefined);
    if (typeof scenario === "string" && scenario !== "live_waiting") {
      state.scenario = scenario;
    } else if (scenario === "live_waiting") {
      state.scenario = null;
    }
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
