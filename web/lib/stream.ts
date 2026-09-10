import type { ResearchDepth, StreamEvent } from "./types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface AskIdentity {
  employee_id: string;
  role: string;
  employee_region?: string | null;
  employee_branch?: string | null;
}

/**
 * Consumes POST /ask/stream as Server-Sent Events. EventSource can't send
 * a POST body, so this parses the `data: ...\n\n` framing directly off a
 * fetch() ReadableStream — the browser-native alternative for a streamed
 * POST.
 */
export async function* streamAsk(
  question: string,
  sessionId: string,
  identity: AskIdentity,
  researchDepth: ResearchDepth = "standard",
  signal?: AbortSignal
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${API_BASE_URL}/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      question,
      identity,
      research_depth: researchDepth,
    }),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`Request failed with status ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      const jsonText = line.slice(5).trim();
      if (!jsonText) continue;
      yield JSON.parse(jsonText) as StreamEvent;
    }
  }
}

export function downloadUrl(sessionId: string): string {
  return `${API_BASE_URL}/download/${sessionId}`;
}
