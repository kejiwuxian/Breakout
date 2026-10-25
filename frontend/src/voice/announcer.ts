/**
 * Announcer captions + queued audio from /ws/events { type: "voice" }.
 * Simulated badge when the payload is simulated; mute skips playback only.
 */
import strings from "../copy/strings.json";

export type VoicePayload = {
  text?: string;
  audio_url?: string | null;
  simulated?: boolean;
  seq?: number;
  alert_id?: string;
};

export type VoiceEvent = {
  type?: string;
  simulated?: boolean;
  payload?: VoicePayload;
  caption?: string;
};

type AnnouncerHost = {
  root: HTMLElement;
  caption: HTMLElement;
  simBadge: HTMLElement;
  muteBtn: HTMLButtonElement;
  audio: HTMLAudioElement;
};

let host: AnnouncerHost | null = null;
let queue: VoicePayload[] = [];
let playing = false;
let muted = false;

function buildPanel(root: HTMLElement): void {
  root.classList.add("panel", "voice-panel");
  root.setAttribute("aria-labelledby", "voice-title");
  root.innerHTML = `
    <header class="panel-head">
      <h2 id="voice-title">${strings.voiceTitle}</h2>
      <span class="badge simulated" data-role="voice-sim" hidden>${strings.simulatedBadge}</span>
    </header>
    <p class="voice-caption" data-role="voice-caption" id="voice-caption" aria-live="polite"></p>
    <div class="voice-controls">
      <button type="button" class="voice-mute" data-role="voice-mute">${strings.voiceMute}</button>
    </div>
    <audio id="voice-audio" playsinline hidden></audio>
    <div data-role="judge-slot" class="judge-slot"></div>
  `;
}

function ensureHost(preferred?: HTMLElement | null): AnnouncerHost {
  if (host) return host;

  let root =
    preferred ||
    document.querySelector<HTMLElement>("#panel-voice") ||
    document.querySelector<HTMLElement>("#voice-panel");
  if (!root) {
    root = document.createElement("section");
    const side = document.querySelector(".dash-side");
    if (side) side.prepend(root);
    else document.body.appendChild(root);
  }
  // Stable id for e2e / caption hooks (even when mounted into #panel-voice).
  root.id = "voice-panel";

  if (!root.querySelector("[data-role=voice-caption]")) {
    buildPanel(root);
  }

  const caption = root.querySelector<HTMLElement>("[data-role=voice-caption]")!;
  const simBadge = root.querySelector<HTMLElement>("[data-role=voice-sim]")!;
  const muteBtn = root.querySelector<HTMLButtonElement>("[data-role=voice-mute]")!;
  let audio = root.querySelector<HTMLAudioElement>("#voice-audio");
  if (!audio) {
    audio = document.createElement("audio");
    audio.id = "voice-audio";
    audio.setAttribute("playsinline", "true");
    audio.hidden = true;
    root.appendChild(audio);
  }

  muteBtn.addEventListener("click", () => {
    muted = !muted;
    muteBtn.textContent = muted ? strings.voiceUnmute : strings.voiceMute;
    muteBtn.setAttribute("aria-pressed", muted ? "true" : "false");
    if (muted && !audio.paused) {
      audio.pause();
      playing = false;
      void pump();
    }
  });

  audio.addEventListener("ended", () => {
    playing = false;
    void pump();
  });
  audio.addEventListener("error", () => {
    playing = false;
    void pump();
  });

  host = { root, caption, simBadge, muteBtn, audio };
  return host;
}

async function pump(): Promise<void> {
  if (playing || queue.length === 0) return;
  const next = queue.shift();
  if (!next) return;
  playing = true;
  const ui = ensureHost();
  const text = next.text || "";
  ui.caption.textContent = text;
  ui.simBadge.hidden = !Boolean(next.simulated);

  // Legacy #voice-caption / status hooks for e2e and status line.
  const legacy = document.querySelector<HTMLElement>("#voice-caption");
  if (legacy && legacy !== ui.caption) legacy.textContent = text;
  const status = document.querySelector<HTMLElement>("#status");
  if (status && text) status.textContent = text;

  if (!muted && next.audio_url) {
    try {
      ui.audio.src = next.audio_url;
      await ui.audio.play();
      return;
    } catch {
      // Autoplay blocked or missing clip — captions still show.
    }
  }
  playing = false;
  await new Promise((r) => setTimeout(r, 500));
  void pump();
}

function enqueue(payload: VoicePayload): void {
  queue.push(payload);
  void pump();
}

/** Mount the announcer panel (idempotent). Returns the judge slot host. */
export function mountAnnouncerPanel(container?: HTMLElement | null): HTMLElement {
  const ui = ensureHost(container ?? null);
  return ui.root.querySelector<HTMLElement>("[data-role=judge-slot]")!;
}

export function handleVoiceEvent(event: VoiceEvent): void {
  ensureHost();
  if (event.type !== "voice") return;
  const payload = event.payload || {};
  const text = payload.text || event.caption || "";
  const simulated = Boolean(event.simulated || payload.simulated);
  enqueue({
    text,
    audio_url: payload.audio_url ?? null,
    simulated,
    seq: payload.seq,
    alert_id: payload.alert_id,
  });
}

export function setAnnouncerMuted(value: boolean): void {
  muted = Boolean(value);
  const ui = ensureHost();
  ui.muteBtn.textContent = muted ? strings.voiceUnmute : strings.voiceMute;
  ui.muteBtn.setAttribute("aria-pressed", muted ? "true" : "false");
}

export function connectAnnouncer(
  wsUrl = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/events`,
): () => void {
  ensureHost();
  const status = document.querySelector<HTMLElement>("#status");

  let ws: WebSocket;
  try {
    ws = new WebSocket(wsUrl);
  } catch {
    if (status) status.textContent = strings.disconnected;
    return () => undefined;
  }

  ws.addEventListener("open", () => {
    if (status) status.textContent = strings.connected;
  });

  ws.addEventListener("message", (event) => {
    try {
      const data = JSON.parse(String(event.data)) as VoiceEvent;
      handleVoiceEvent(data);
    } catch {
      // Ignore non-JSON frames.
    }
  });

  ws.addEventListener("close", () => {
    if (status) status.textContent = strings.disconnected;
  });

  return () => {
    try {
      ws.close();
    } catch {
      /* ignore */
    }
  };
}
