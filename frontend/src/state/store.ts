/**
 * Minimal dashboard state fed by /ws/events.
 */
import type { PipelineEvent } from "../ws/events";

export type CandidateRow = {
  star_id: string;
  ra_deg: number;
  dec_deg: number;
  class: string;
  spectral_type: string;
  distance_kpc: number | null;
  extinction_av_mag: number | null;
  p_sky: number;
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

export type ActionsPayload = {
  alert_id?: string;
  lcogt_dry_run?: boolean;
  top_star_id?: string | null;
  lcogt?: {
    path?: string;
    dry_run?: boolean;
    submitted?: boolean;
    request_group?: Record<string, unknown>;
    simulated?: boolean;
  } | null;
  too_hst_markdown?: string | null;
  too_jwst_markdown?: string | null;
  gcn_circular_markdown?: string | null;
  simulated?: boolean;
  note?: string;
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
  actions: ActionsPayload | null;
  actionsSimulated: boolean;
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
  actions: null,
  actionsSimulated: false,
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

export function applyEvent(event: PipelineEvent): void {
  if (typeof event.simulated === "boolean") {
    state.lastSimulated = event.simulated;
  }

  if (event.type === "hello") {
    const flat = event as PipelineEvent & { scenario?: string };
    const scenario = flat.scenario ?? (event.payload?.scenario as string | undefined);
    if (typeof scenario === "string") state.scenario = scenario;
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
    if (state.candidates.length && !state.selectedStarId) {
      state.selectedStarId = state.candidates[0].star_id;
    }
  }

  if (event.type === "actions" && event.payload) {
    state.actions = event.payload as ActionsPayload;
    state.actionsSimulated = Boolean(event.simulated || state.actions.simulated);
  }

  if (event.type === "scenario_done" && event.payload?.scenario) {
    state.scenario = String(event.payload.scenario);
  }

  emit();
}
