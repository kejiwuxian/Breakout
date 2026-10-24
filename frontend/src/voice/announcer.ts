/**
 * Plays announcer audio / captions from /ws/events.
 * Full Grok Voice wiring is filled in a later prompt.
 */
import strings from "../copy/strings.json";

export function connectAnnouncer(wsUrl = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/events`): void {
  const status = document.querySelector<HTMLElement>("#status");
  const simBadge = document.querySelector<HTMLElement>("#sim-badge");

  let ws: WebSocket;
  try {
    ws = new WebSocket(wsUrl);
  } catch {
    if (status) status.textContent = strings.disconnected;
    return;
  }

  ws.addEventListener("open", () => {
    if (status) status.textContent = strings.connected;
  });

  ws.addEventListener("message", (event) => {
    try {
      const data = JSON.parse(String(event.data)) as {
        type?: string;
        simulated?: boolean;
        caption?: string;
      };
      if (data.simulated && simBadge) {
        simBadge.hidden = false;
      }
      if (data.type === "voice" && data.caption && status) {
        status.textContent = data.caption;
      }
    } catch {
      // Ignore non-JSON frames in scaffold.
    }
  });

  ws.addEventListener("close", () => {
    if (status) status.textContent = strings.disconnected;
  });
}
