/**
 * WebSocket client for /ws/events (proxied to ws://localhost:8000).
 */
export type PipelineEvent = {
  type: string;
  payload?: Record<string, unknown>;
  simulated?: boolean;
};

export type EventHandler = (event: PipelineEvent) => void;

const DEFAULT_WS =
  typeof location !== "undefined"
    ? `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/events`
    : "ws://localhost:8000/ws/events";

export function connectEvents(
  onEvent: EventHandler,
  onStatus?: (state: "connecting" | "open" | "closed") => void,
  url = DEFAULT_WS,
): () => void {
  onStatus?.("connecting");
  const ws = new WebSocket(url);

  ws.addEventListener("open", () => onStatus?.("open"));
  ws.addEventListener("close", () => onStatus?.("closed"));
  ws.addEventListener("message", (msg) => {
    try {
      const data = JSON.parse(String(msg.data)) as PipelineEvent;
      onEvent(data);
    } catch {
      // Ignore non-JSON frames.
    }
  });

  return () => {
    try {
      ws.close();
    } catch {
      /* ignore */
    }
  };
}
