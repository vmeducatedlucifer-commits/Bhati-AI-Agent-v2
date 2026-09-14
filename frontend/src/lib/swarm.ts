import { API } from "./api"

export type AgentRecord = {
  id: string
  role: string
  team: string
  status: "idle" | "working" | "waiting" | "blocked" | "done" | "failed"
  task_id: string | null
  current_action: string
  model: string | null
  steps: number
  tokens: number
  messages_sent: number
  uptime: number
}

export type A2AMessage = {
  id: string
  sender: string
  recipient: string
  kind: string
  content: string
  topic: string
  timestamp: number
}

export type BoardEntry = {
  id: string
  key: string
  value: unknown
  author: string
  kind: string
  confidence: number
  version: number
  updated_at: number
}

export type SwarmRun = {
  id: string
  goal: string
  size: number
  status: string
  output: string
  elapsed: number
  teams: { name: string; objective: string; lead: string | null; size: number }[]
  plan: { tasks: { id: string; title: string; status: string; agent: string }[] } | null
  scheduler: {
    submitted: number
    completed: number
    failed: number
    in_flight: number
    peak_in_flight: number
    throughput_per_min: number
  } | null
}

export type SwarmSummary = {
  total: number
  active: number
  by_status: Record<string, number>
  by_role: Record<string, number>
  by_team: Record<string, number>
  tokens: number
  steps: number
}

export type Snapshot = {
  agents: AgentRecord[]
  summary: SwarmSummary
  messages: A2AMessage[]
  message_stats: { total_messages: number; by_kind: Record<string, number> }
  blackboard: BoardEntry[]
  runs: SwarmRun[]
}

export type BoardTask = {
  id: string
  title: string
  description: string
  acceptance: string
  priority: number
  assignee: string
  mode: string
  size: number | null
  model: string | null
  status: string
  progress: number
  agent_ids: string[]
  run_id: string | null
  result: string
  tags: string[]
  log: { at: number; author: string; message: string }[]
}

export const EMPTY_SNAPSHOT: Snapshot = {
  agents: [],
  summary: {
    total: 0,
    active: 0,
    by_status: {},
    by_role: {},
    by_team: {},
    tokens: 0,
    steps: 0,
  },
  messages: [],
  message_stats: { total_messages: 0, by_kind: {} },
  blackboard: [],
  runs: [],
}

const array = <T,>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : [])
const record = (value: unknown): Record<string, number> =>
  value && typeof value === "object" ? (value as Record<string, number>) : {}

/** Never throws and never returns a partially shaped object — the dashboard
 *  renders straight from this, so a backend error must not crash the client. */
export function normalizeSnapshot(raw: unknown): Snapshot {
  if (!raw || typeof raw !== "object") return EMPTY_SNAPSHOT
  const data = raw as Record<string, unknown>
  const summary = (data.summary ?? {}) as Record<string, unknown>
  const stats = (data.message_stats ?? {}) as Record<string, unknown>

  return {
    agents: array<AgentRecord>(data.agents),
    summary: {
      total: Number(summary.total ?? 0),
      active: Number(summary.active ?? 0),
      by_status: record(summary.by_status),
      by_role: record(summary.by_role),
      by_team: record(summary.by_team),
      tokens: Number(summary.tokens ?? 0),
      steps: Number(summary.steps ?? 0),
    },
    messages: array<A2AMessage>(data.messages).filter((message) => message && message.id),
    message_stats: {
      total_messages: Number(stats.total_messages ?? 0),
      by_kind: record(stats.by_kind),
    },
    blackboard: array<BoardEntry>(data.blackboard),
    runs: array<SwarmRun>(data.runs),
  }
}

async function safeJson(url: string): Promise<unknown> {
  try {
    const res = await fetch(url)
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

export async function getSnapshot(sessionId: string): Promise<Snapshot> {
  return normalizeSnapshot(await safeJson(`${API}/api/swarm/snapshot/${sessionId}`))
}

export async function launchSwarm(body: {
  session_id: string
  goal: string
  size?: number
  model?: string | null
}) {
  const res = await fetch(`${API}/api/swarm/launch`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`Launch failed (${res.status})`)
  return res.json()
}

export async function cancelRun(runId: string) {
  await fetch(`${API}/api/swarm/runs/${runId}/cancel`, { method: "POST" }).catch(() => undefined)
}

export async function runDebate(sessionId: string, question: string) {
  const res = await fetch(`${API}/api/swarm/debate`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, question }),
  })
  return res.json().catch(() => null)
}

/** Live SSE feed of agent-to-agent messages. Returns a cleanup function. */
export function streamConversation(
  sessionId: string,
  onMessage: (message: A2AMessage) => void,
): () => void {
  if (typeof window === "undefined" || typeof EventSource === "undefined") return () => undefined
  let source: EventSource | null = null
  try {
    source = new EventSource(`${API}/api/swarm/stream/${sessionId}`)
  } catch {
    return () => undefined
  }
  source.onmessage = (event) => {
    try {
      const parsed = JSON.parse(event.data)
      if (parsed && parsed.id) onMessage(parsed as A2AMessage)
    } catch {
      /* keepalive */
    }
  }
  source.onerror = () => source?.close()
  return () => source?.close()
}

// ------------------------------------------------------------------ tasks
export async function listTasks(sessionId: string) {
  const data = (await safeJson(`${API}/api/tasks?session_id=${sessionId}`)) as
    | { tasks?: BoardTask[]; stats?: Record<string, unknown> }
    | null
  return {
    tasks: array<BoardTask>(data?.tasks).map((task) => ({
      ...task,
      agent_ids: array<string>(task.agent_ids),
      tags: array<string>(task.tags),
      log: array<BoardTask["log"][number]>(task.log),
      progress: Number(task.progress ?? 0),
    })),
    stats: data?.stats ?? {},
  }
}

export async function createTask(body: Record<string, unknown>) {
  const res = await fetch(`${API}/api/tasks`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`Create task failed (${res.status})`)
  return res.json() as Promise<BoardTask>
}

export async function startTask(id: string) {
  await fetch(`${API}/api/tasks/${id}/start`, { method: "POST" }).catch(() => undefined)
}

export async function cancelTask(id: string) {
  await fetch(`${API}/api/tasks/${id}/cancel`, { method: "POST" }).catch(() => undefined)
}

export async function deleteTask(id: string) {
  await fetch(`${API}/api/tasks/${id}`, { method: "DELETE" }).catch(() => undefined)
}

export async function startAll(sessionId: string) {
  await fetch(`${API}/api/tasks/start-all/${sessionId}`, { method: "POST" }).catch(() => undefined)
}

// ----------------------------------------------------------------- models
export async function listModels() {
  const data = (await safeJson(`${API}/api/models`)) as
    | { providers?: string[]; models?: unknown[]; defaults?: Record<string, string> }
    | null
  return {
    providers: array<string>(data?.providers),
    models: array<{ id: string; type: string; custom: boolean }>(data?.models).filter(
      (model) => model && model.id,
    ),
    defaults: data?.defaults ?? {},
  }
}

export async function addCustomModel(body: Record<string, unknown>) {
  const res = await fetch(`${API}/api/models/custom`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `Failed (${res.status})`)
  }
  return res.json()
}

export async function deleteCustomModel(alias: string) {
  await fetch(`${API}/api/models/custom/${alias}`, { method: "DELETE" }).catch(() => undefined)
}

export async function testModel(model: string) {
  const res = await fetch(`${API}/api/models/test`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ model }),
  })
  return res.json().catch(() => ({ ok: false }))
}
