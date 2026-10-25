/**
 * Voice captions + mute + optional push-to-talk (same backend contracts).
 */
import strings from "../copy/strings.json";
import { getState, setVoiceCaption, subscribe } from "../state/store";
import type { PipelineEvent } from "../ws/events";

type VoicePayload = {
  text?: string;
  audio_url?: string | null;
  simulated?: boolean;
};

let queue: VoicePayload[] = [];
let playing = false;
let muted = false;
let audioEl: HTMLAudioElement | null = null;

async function pump(captionEl: HTMLElement, simEl: HTMLElement): Promise<void> {
  if (playing || queue.length === 0) return;
  const next = queue.shift();
  if (!next) return;
  playing = true;
  const text = next.text || "";
  captionEl.textContent = text;
  simEl.hidden = !Boolean(next.simulated);
  setVoiceCaption(text, Boolean(next.simulated));

  if (!muted && next.audio_url && audioEl) {
    try {
      audioEl.src = next.audio_url;
      await audioEl.play();
      return;
    } catch {
      /* captions still show */
    }
  }
  playing = false;
  await new Promise((r) => setTimeout(r, 450));
  void pump(captionEl, simEl);
}

export function handleVoiceEvent(event: PipelineEvent): void {
  if (event.type !== "voice") return;
  const payload = (event.payload || {}) as VoicePayload;
  const text = payload.text || "";
  queue.push({
    text,
    audio_url: payload.audio_url ?? null,
    simulated: Boolean(event.simulated || payload.simulated),
  });
  const caption = document.querySelector<HTMLElement>("[data-role=voice-caption]");
  const sim = document.querySelector<HTMLElement>("[data-role=voice-sim]");
  if (caption && sim) void pump(caption, sim);
}

export function resetVoicePlayback(): void {
  queue = [];
  playing = false;
  if (audioEl) {
    audioEl.pause();
    audioEl.removeAttribute("src");
    audioEl.load();
  }
}

export function mountVoice(host: HTMLElement): () => void {
  host.innerHTML = `
    <div class="rail-block voice">
      <div class="rail-head">
        <h2 class="rail-title">${strings.voiceTitle}</h2>
        <span class="badge sim" data-role="voice-sim" hidden>${strings.simulatedBadge}</span>
      </div>
      <p class="voice-caption" data-role="voice-caption" id="voice-caption" aria-live="polite"></p>
      <div class="voice-controls">
        <button type="button" class="ghost-btn" data-role="mute">${strings.voiceMute}</button>
        <button type="button" class="ghost-btn judge-ptt" data-role="ptt">${strings.voiceAsk}</button>
      </div>
      <p class="judge-hint">${strings.voiceAskHint}</p>
      <p class="judge-transcript" data-role="transcript" aria-live="polite"></p>
      <p class="judge-error" data-role="error" hidden></p>
      <audio data-role="audio" playsinline hidden></audio>
    </div>
  `;

  const caption = host.querySelector<HTMLElement>("[data-role=voice-caption]")!;
  const sim = host.querySelector<HTMLElement>("[data-role=voice-sim]")!;
  const muteBtn = host.querySelector<HTMLButtonElement>("[data-role=mute]")!;
  const ptt = host.querySelector<HTMLButtonElement>("[data-role=ptt]")!;
  const transcript = host.querySelector<HTMLElement>("[data-role=transcript]")!;
  const error = host.querySelector<HTMLElement>("[data-role=error]")!;
  audioEl = host.querySelector<HTMLAudioElement>("[data-role=audio]")!;

  audioEl.addEventListener("ended", () => {
    playing = false;
    void pump(caption, sim);
  });
  audioEl.addEventListener("error", () => {
    playing = false;
    void pump(caption, sim);
  });

  muteBtn.addEventListener("click", () => {
    muted = !muted;
    muteBtn.textContent = muted ? strings.voiceUnmute : strings.voiceMute;
    if (muted && audioEl && !audioEl.paused) {
      audioEl.pause();
      playing = false;
      void pump(caption, sim);
    }
  });

  // Lazy-load judge Q&A so announcer still works if realtime fails.
  let judge: { startTalk: () => Promise<void>; stopTalk: () => void } | null =
    null;
  const ensureJudge = async () => {
    if (judge) return judge;
    const mod = await import("../voice/judge_qa");
    judge = mod.createJudgeQaSession({
      btn: ptt,
      transcript,
      error,
    });
    return judge;
  };

  const onDown = (ev: Event) => {
    ev.preventDefault();
    void ensureJudge()
      .then((s) => s.startTalk())
      .catch(() => {
        /* error shown in panel; announcer unaffected */
      });
  };
  const onUp = (ev: Event) => {
    ev.preventDefault();
    judge?.stopTalk();
  };
  ptt.addEventListener("mousedown", onDown);
  ptt.addEventListener("mouseup", onUp);
  ptt.addEventListener("mouseleave", onUp);
  ptt.addEventListener("touchstart", onDown, { passive: false });
  ptt.addEventListener("touchend", onUp);

  const unsub = subscribe(() => {
    const { voiceCaption, voiceSimulated } = getState();
    caption.textContent = voiceCaption;
    sim.hidden = !voiceCaption || !voiceSimulated;
  });

  return () => {
    unsub();
    judge?.stopTalk();
  };
}
