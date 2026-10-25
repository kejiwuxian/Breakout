/**
 * Plays announcer audio / captions from /ws/events voice events.
 */
import strings from "../copy/strings.json";

type VoicePayload = {
  text?: string;
  audio_url?: string | null;
  simulated?: boolean;
  seq?: number;
  alert_id?: string;
};

type VoiceEvent = {
  type?: string;
  simulated?: boolean;
  payload?: VoicePayload;
  caption?: string;
};

let captionEl: HTMLElement | null = null;
let audioEl: HTMLAudioElement | null = None;
let queue: VoicePayload[] = [];
let playing = false;

function ensureUi(): void {
  if (!captionEl) {
    captionEl = document.querySelector<HTMLElement>("#voice-caption");
  }
  if (!audioEl) {
    audioEl = document.querySelector<HTMLAudioElement>("#voice-audio");
    if (!audioEl) {
      audioEl = document.createElement("audio");
      audioEl.id = "voice-audio";
      audioEl.setAttribute("playsinline", "true");
      document.body.appendChild(audioEl);
    }
    audioEl.addEventListener("ended", () => {
      playing = false;
      void pump();
    });
    audioEl.addEventListener("error", () => {
      playing = false;
      void pump();
    });
  }
}

async function pump(): Promise<void> {
  if (playing || queue.length === 0) return;
  const next = queue.shift();
  if (!next) return;
  playing = true;
  ensureUi();
  const text = next.text || "";
  if (captionEl) captionEl.textContent = text;
  const status = document.querySelector<HTMLElement>("#status");
  if (status && text) status.textContent = text;

  if (next.audio_url && audioEl) {
    try {
      audioEl.src = next.audio_url;
      await audioEl.play();
      return;
    } catch {
      // Autoplay may be blocked; captions still show.
    }
  }
  playing = false;
  // Brief pause so captions are readable when audio is unavailable.
  await new Promise((r) => setTimeout(r, 600));
  void pump();
}

function enqueue(payload: VoicePayload): void {
  queue.push(payload);
  void pump();
}

/**
 * Prefer the shared dashboard WebSocket by hooking applyEvent callers.
 * Also supports a dedicated socket when invoked standalone.
 */
export function handleVoiceEvent(event: VoiceEvent): void {
  ensureUi();
  const simBadge = document.querySelector<HTMLElement>("#sim-badge");
  if ((event.simulated || event.payload?.simulated) && simBadge) {
    simBadge.hidden = false;
  }
  if (event.type !== "voice") return;
  const payload = event.payload || {};
  const text = payload.text || event.caption || "";
  enqueue({
    text,
    audio_url: payload.audio_url ?? null,
    simulated: Boolean(event.simulated || payload.simulated),
    seq: payload.seq,
    alert_id: payload.alert_id,
  });
}

export function connectAnnouncer(
  wsUrl = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/events`,
): () => void {
  ensureUi();
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
