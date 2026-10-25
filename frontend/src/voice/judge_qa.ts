/**
 * Push-to-talk judge Q&A over Grok Voice realtime.
 *
 * Browser never sees XAI_API_KEY: POST /voice/session mints a token, then
 * connects to wss://api.x.ai/v1/realtime?model=… with subprotocol
 * xai-client-secret.<token>. Tools call Light's GET /voice/tools/<name>.
 * Realtime failure surfaces an error but does not stop the announcer.
 */
import strings from "../copy/strings.json";

const SAMPLE_RATE = 24_000;
const REALTIME_BASE = "wss://api.x.ai/v1/realtime";

/** Function tools only — no web_search / x_search / file_search / mcp. */
const TOOL_SPECS_CLIENT = [
  {
    type: "function",
    name: "get_top_candidates",
    description:
      "Return top ranked candidates with ADS bibcodes and simulated flags.",
    parameters: {
      type: "object",
      properties: {
        limit: { type: "integer", description: "Max candidates (default 5)." },
      },
    },
  },
  {
    type: "function",
    name: "get_skymap_summary",
    description: "Return fused sky map peak and credible region summary.",
    parameters: { type: "object", properties: {} },
  },
  {
    type: "function",
    name: "get_breakout_countdown",
    description: "Return breakout class window and countdown for a candidate.",
    parameters: {
      type: "object",
      properties: {
        star_id: {
          type: "string",
          description: "Optional star_id; defaults to the top candidate.",
        },
      },
    },
  },
] as const;

export type SessionInfo = {
  token: string;
  model: string;
  voice: string;
};

export type JudgeQaSession = {
  connect: () => Promise<void>;
  disconnect: () => void;
  startTalk: () => Promise<void>;
  stopTalk: () => void;
};

type JudgeUi = {
  btn: HTMLButtonElement;
  transcript: HTMLElement;
  error: HTMLElement;
};

function pcm16Base64FromFloat32(input: Float32Array): string {
  const buf = new ArrayBuffer(input.length * 2);
  const view = new DataView(buf);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]!));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  const bytes = new Uint8Array(buf);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]!);
  return btoa(binary);
}

function base64ToInt16(b64: string): Int16Array {
  const binary = atob(b64);
  const out = new Int16Array(binary.length / 2);
  for (let i = 0; i < out.length; i++) {
    const lo = binary.charCodeAt(i * 2);
    const hi = binary.charCodeAt(i * 2 + 1);
    out[i] = (hi << 8) | lo;
    if (out[i]! >= 0x8000) out[i]! -= 0x10000;
  }
  return out;
}

async function fetchSession(): Promise<SessionInfo> {
  const res = await fetch("/voice/session", { method: "POST" });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `POST /voice/session failed (${res.status})`);
  }
  const data = (await res.json()) as {
    token?: string;
    model?: string;
    voice?: string;
  };
  if (!data.token || !data.model) {
    throw new Error("POST /voice/session missing token or model");
  }
  return {
    token: data.token,
    model: data.model,
    voice: data.voice || "eve",
  };
}

async function callTool(
  name: string,
  argsJson: string,
): Promise<Record<string, unknown>> {
  let args: Record<string, unknown> = {};
  try {
    args = argsJson ? (JSON.parse(argsJson) as Record<string, unknown>) : {};
  } catch {
    args = {};
  }
  const params = new URLSearchParams();
  if (name === "get_top_candidates" && args.limit != null) {
    params.set("limit", String(args.limit));
  }
  if (name === "get_breakout_countdown" && args.star_id != null) {
    params.set("star_id", String(args.star_id));
  }
  const qs = params.toString();
  const url = `/voice/tools/${encodeURIComponent(name)}${qs ? `?${qs}` : ""}`;
  const res = await fetch(url);
  if (!res.ok) {
    const detail = await res.text();
    return {
      error: detail || `tool ${name} failed (${res.status})`,
      simulated: false,
    };
  }
  return (await res.json()) as Record<string, unknown>;
}

const JUDGE_INSTRUCTIONS =
  "You are mission control for BREAKOUT. Answer only from tool results. " +
  "Name the ADS bibcode for every literature claim. " +
  "When a value or candidate is simulated, say the word simulated. " +
  "Do not invent numbers, citations, or sky positions. No web search.";

export function createJudgeQaSession(ui: JudgeUi): JudgeQaSession {
  let ws: WebSocket | null = null;
  let mediaStream: MediaStream | null = null;
  let audioCtx: AudioContext | null = null;
  let processor: ScriptProcessorNode | null = null;
  let source: MediaStreamAudioSourceNode | null = null;
  let talking = false;
  let playCtx: AudioContext | null = null;
  let nextPlayTime = 0;
  let sessionVoice = "eve";

  const setError = (msg: string) => {
    ui.error.hidden = !msg;
    ui.error.textContent = msg;
  };

  const appendTranscript = (chunk: string) => {
    if (!chunk) return;
    ui.transcript.textContent = `${ui.transcript.textContent || ""}${chunk}`;
  };

  const playPcm16Chunk = (b64: string) => {
    try {
      const samples = base64ToInt16(b64);
      if (!samples.length) return;
      if (!playCtx) {
        playCtx = new AudioContext({ sampleRate: SAMPLE_RATE });
        nextPlayTime = playCtx.currentTime;
      }
      const f32 = new Float32Array(samples.length);
      for (let i = 0; i < samples.length; i++) {
        f32[i] = (samples[i] ?? 0) / 32768;
      }
      const buf = playCtx.createBuffer(1, f32.length, SAMPLE_RATE);
      buf.copyToChannel(f32, 0);
      const node = playCtx.createBufferSource();
      node.buffer = buf;
      node.connect(playCtx.destination);
      const startAt = Math.max(playCtx.currentTime, nextPlayTime);
      node.start(startAt);
      nextPlayTime = startAt + buf.duration;
    } catch {
      // Keep transcript even if audio playback fails.
    }
  };

  const sendJson = (obj: unknown) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    }
  };

  const sendSessionUpdate = () => {
    sendJson({
      type: "session.update",
      session: {
        voice: sessionVoice,
        instructions: JUDGE_INSTRUCTIONS,
        turn_detection: { type: "server_vad" },
        tools: TOOL_SPECS_CLIENT,
        // No web_search / x_search / file_search / mcp — tools only.
      },
    });
  };

  const handleServerEvent = async (raw: string) => {
    let event: Record<string, unknown>;
    try {
      event = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return;
    }
    const type = String(event.type || "");

    if (type === "session.created" || type === "session.updated") {
      // Ensure our tool set is applied after the server creates the session.
      if (type === "session.created") sendSessionUpdate();
      return;
    }

    if (type === "response.output_audio.delta" && typeof event.delta === "string") {
      playPcm16Chunk(event.delta);
      return;
    }

    if (
      (type === "response.output_audio_transcript.delta" ||
        type === "response.audio_transcript.delta") &&
      typeof event.delta === "string"
    ) {
      appendTranscript(event.delta);
      return;
    }

    if (type === "response.function_call_arguments.done") {
      const name = String(event.name || "");
      const callId = String(event.call_id || "");
      const args = typeof event.arguments === "string" ? event.arguments : "{}";
      if (!name || !callId) return;
      const result = await callTool(name, args);
      sendJson({
        type: "conversation.item.create",
        item: {
          type: "function_call_output",
          call_id: callId,
          output: JSON.stringify(result),
        },
      });
      sendJson({ type: "response.create" });
      return;
    }

    if (type === "error") {
      const err = event.error as { message?: string } | undefined;
      setError(err?.message || strings.voiceRealtimeError);
    }
  };

  const stopMic = () => {
    talking = false;
    ui.btn.classList.remove("is-talking");
    ui.btn.textContent = strings.voiceAsk;
    try {
      processor?.disconnect();
      source?.disconnect();
    } catch {
      /* ignore */
    }
    processor = null;
    source = null;
    if (audioCtx) {
      void audioCtx.close().catch(() => undefined);
      audioCtx = null;
    }
    if (mediaStream) {
      for (const track of mediaStream.getTracks()) track.stop();
      mediaStream = null;
    }
  };

  const disconnect = () => {
    stopMic();
    if (ws) {
      try {
        ws.close();
      } catch {
        /* ignore */
      }
      ws = null;
    }
    if (playCtx) {
      void playCtx.close().catch(() => undefined);
      playCtx = null;
    }
  };

  const connect = async () => {
    setError("");
    ui.transcript.textContent = "";
    let info: SessionInfo;
    try {
      info = await fetchSession();
    } catch (err) {
      setError(
        `${strings.voiceRealtimeError}: ${err instanceof Error ? err.message : String(err)}`,
      );
      throw err;
    }
    sessionVoice = info.voice || "eve";

    return new Promise<void>((resolve, reject) => {
      try {
        ws = new WebSocket(`${REALTIME_BASE}?model=${encodeURIComponent(info.model)}`, [
          `xai-client-secret.${info.token}`,
        ]);
      } catch (err) {
        setError(
          `${strings.voiceRealtimeError}: ${err instanceof Error ? err.message : String(err)}`,
        );
        reject(err);
        return;
      }

      const fail = (msg: string) => {
        setError(msg);
        disconnect();
        reject(new Error(msg));
      };

      const timer = window.setTimeout(() => {
        fail(strings.voiceRealtimeTimeout);
      }, 12_000);

      ws.addEventListener("open", () => {
        sendSessionUpdate();
      });

      ws.addEventListener("message", (ev) => {
        void handleServerEvent(String(ev.data)).then(() => {
          // Resolve once we have a live socket; session.created may already have fired.
        });
      });

      ws.addEventListener("error", () => {
        window.clearTimeout(timer);
        fail(strings.voiceRealtimeError);
      });

      ws.addEventListener("close", () => {
        window.clearTimeout(timer);
        ws = null;
      });

      // Resolve after open so PTT can proceed; errors still surface in the panel.
      ws.addEventListener(
        "open",
        () => {
          window.clearTimeout(timer);
          resolve();
        },
        { once: true },
      );
    });
  };

  const startTalk = async () => {
    setError("");
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      try {
        await connect();
      } catch {
        // Error already shown; announcer keeps working.
        return;
      }
    }
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
    } catch (err) {
      setError(
        `${strings.voiceMicError}: ${err instanceof Error ? err.message : String(err)}`,
      );
      return;
    }

    audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE });
    source = audioCtx.createMediaStreamSource(mediaStream);
    // ScriptProcessor is deprecated but widely available without a worklet file.
    processor = audioCtx.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (ev) => {
      if (!talking || !ws || ws.readyState !== WebSocket.OPEN) return;
      const input = ev.inputBuffer.getChannelData(0);
      const b64 = pcm16Base64FromFloat32(input);
      sendJson({ type: "input_audio_buffer.append", audio: b64 });
    };
    source.connect(processor);
    processor.connect(audioCtx.destination);
    talking = true;
    ui.btn.classList.add("is-talking");
    ui.btn.textContent = strings.voiceListening;
  };

  const stopTalk = () => {
    stopMic();
  };

  return { connect, disconnect, startTalk, stopTalk };
}

/** Mount push-to-talk UI into a host element. Announcer keeps working on errors. */
export function mountJudgeQa(host: HTMLElement): () => void {
  host.innerHTML = `
    <div class="judge-qa">
      <button type="button" class="judge-ptt" data-role="ptt">${strings.voiceAsk}</button>
      <p class="judge-hint">${strings.voiceAskHint}</p>
      <p class="judge-transcript" data-role="transcript" aria-live="polite"></p>
      <p class="judge-error" data-role="error" hidden></p>
    </div>
  `;
  const btn = host.querySelector<HTMLButtonElement>("[data-role=ptt]")!;
  const transcript = host.querySelector<HTMLElement>("[data-role=transcript]")!;
  const error = host.querySelector<HTMLElement>("[data-role=error]")!;
  const session = createJudgeQaSession({ btn, transcript, error });

  const onDown = (ev: Event) => {
    ev.preventDefault();
    void session.startTalk();
  };
  const onUp = (ev: Event) => {
    ev.preventDefault();
    session.stopTalk();
  };

  btn.addEventListener("mousedown", onDown);
  btn.addEventListener("mouseup", onUp);
  btn.addEventListener("mouseleave", onUp);
  btn.addEventListener("touchstart", onDown, { passive: false });
  btn.addEventListener("touchend", onUp);

  return () => {
    session.disconnect();
    host.innerHTML = "";
  };
}
