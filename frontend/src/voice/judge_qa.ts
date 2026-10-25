/**
 * Mic → Grok Voice realtime → spoken answers via backend tools.
 * Placeholder — filled in a later prompt (Tony).
 */

export type JudgeQaSession = {
  connect: () => Promise<void>;
  disconnect: () => void;
};

export function createJudgeQaSession(): JudgeQaSession {
  return {
    async connect(): Promise<void> {
      throw new Error("createJudgeQaSession.connect is filled in a later prompt.");
    },
    disconnect(): void {
      // no-op scaffold
    },
  };
}
