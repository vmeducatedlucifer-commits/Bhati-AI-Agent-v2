/**
 * Typed API client for the Bhati backend.
 * Base URL comes from NEXT_PUBLIC_API_URL (Render) and falls back to localhost.
 */

export const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/$/, "");

export const api = (path: string) => `${API_BASE}/api${path}`;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(api(path), {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${detail.slice(0, 300)}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const get = <T,>(path: string) => request<T>(path);
export const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
export const patch = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined });
export const del = <T,>(path: string) => request<T>(path, { method: "DELETE" });

/* ------------------------------------------------------------------ types */

export type HealthInfo = {
  status?: string;
  version?: string;
  providers?: string[];
  [key: string]: unknown;
};

export type ModelEntry = {
  id: string;
  type?: string;
  label?: string;
  model?: string;
  custom?: boolean;
  requires_api_key?: boolean;
};

export type FileNode = {
  name: string;
  path: string;
  type: "file" | "dir";
  size: number;
  modified: number;
  mime?: string;
  children?: FileNode[];
};

export type WorkspaceAgent = {
  agent_id: string;
  path: string;
  files: number;
  bytes: number;
  modified: number;
  special?: boolean;
};

export type WorkspaceStats = {
  session_id: string;
  path: string;
  files: number;
  bytes: number;
  modified: number;
  ephemeral: boolean;
  agents: WorkspaceAgent[];
};

export type WorkspaceSession = {
  session_id: string;
  files: number;
  bytes: number;
  modified: number;
  agents: number;
};

export type FilePreview = {
  path: string;
  name: string;
  size: number;
  modified: number;
  mime: string;
  text: string | null;
  binary: boolean;
  truncated: boolean;
};

export type SwarmAgent = {
  id: string;
  role: string;
  team: string;
  status: string;
  steps?: number;
  tokens?: number;
  current_action?: string;
  model?: string;
};

export type SwarmMessage = {
  id?: string;
  sender: string;
  recipient?: string | null;
  topic?: string;
  kind: string;
  content: string;
  ts?: number;
};

/* ------------------------------------------------------------- endpoints */

export const health = () => get<HealthInfo>("/health");
export const info = () => get<HealthInfo>("/info");
export const listModels = () => get<{ models?: ModelEntry[]; providers?: string[] }>("/models");

export const workspace = {
  sessions: () => get<{ sessions: WorkspaceSession[] }>("/workspace"),
  overview: (sessionId: string) => get<WorkspaceStats>(`/workspace/${sessionId}`),
  tree: (sessionId: string, path = "", agentId?: string) =>
    get<{ session_id: string; path: string; nodes: FileNode[] }>(
      `/workspace/${sessionId}/tree?path=${encodeURIComponent(path)}${
        agentId ? `&agent_id=${encodeURIComponent(agentId)}` : ""
      }`,
    ),
  preview: (sessionId: string, path: string) =>
    get<FilePreview>(`/workspace/${sessionId}/file?path=${encodeURIComponent(path)}`),
  downloadUrl: (sessionId: string, path: string) =>
    api(`/workspace/${sessionId}/download?path=${encodeURIComponent(path)}`),
  archiveUrl: (sessionId: string, path = "") =>
    api(`/workspace/${sessionId}/archive?path=${encodeURIComponent(path)}`),
  remove: (sessionId: string, path: string) =>
    del<{ deleted: string }>(`/workspace/${sessionId}/file?path=${encodeURIComponent(path)}`),
  upload: async (sessionId: string, file: File, path = "") => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(
      api(`/workspace/${sessionId}/upload?path=${encodeURIComponent(path)}`),
      { method: "POST", body: form },
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
};

export const swarmApi = {
  config: () => get<Record<string, unknown>>("/swarm/config"),
  launch: (body: Record<string, unknown>) => post<Record<string, unknown>>("/swarm/launch", body),
  snapshot: (sessionId: string) =>
    get<{ agents: SwarmAgent[]; messages: SwarmMessage[]; summary?: Record<string, number> }>(
      `/swarm/snapshot/${sessionId}`,
    ),
  graph: (sessionId: string) => get<Record<string, unknown>>(`/swarm/graph/${sessionId}`),
  cancel: (runId: string) => post(`/swarm/runs/${runId}/cancel`),
};

/* ------------------------------------------------------------------- SSE */

export function subscribeEvents(
  sessionId: string,
  onEvent: (event: { type: string; data: Record<string, unknown>; agent_id?: string }) => void,
): () => void {
  const source = new EventSource(api(`/events/${sessionId}`));
  source.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data));
    } catch {
      /* ignore keepalives */
    }
  };
  source.onerror = () => source.close();
  return () => source.close();
}

/** Stream a chat reply. Falls back to a single JSON response when SSE is off. */
export async function streamChat(
  body: Record<string, unknown>,
  onToken: (text: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(api("/chat/stream"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const fallback = await post<{ output?: string; content?: string }>("/chat", body);
    onToken(fallback.output || fallback.content || "");
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      for (const line of part.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const raw = line.slice(5).trim();
        if (!raw || raw === "[DONE]") continue;
        try {
          const parsed = JSON.parse(raw);
          const text =
            parsed.text ?? parsed.delta ?? parsed.content ?? parsed?.data?.text ?? "";
          if (text) onToken(String(text));
        } catch {
          onToken(raw);
        }
      }
    }
  }
}
