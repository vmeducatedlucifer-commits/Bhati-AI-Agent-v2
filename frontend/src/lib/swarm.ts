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

export type Snapshot = {
  agents: AgentRecord[]
  summary: {
    total: number
    active: number
    by_status: Record<string, number>
    by_role: Record<string, number>
    by_team: Record<string, number>
    tokens: number
    steps: number
  }
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

export async function getSnapshot(sessionId: string): Promise<Snapshot> {
  const res = await fetch(`${API}/api/swarm/snapshot/${sessionId}`)
  return res.json()
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
  return res.json()
}

export async function cancelRun(runId: string) {
  await fetch(`${API}/api/swarm/runs/${runId}/cancel`, { method: "POST" })
}

export async function runDebate(sessionId: string, question: string) {
  const res = await fetch(`${API}/api/swarm/debate`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, question }),
  })
  return res.json()
}

/** Live SSE feed of agent-to-agent messages. Returns a cleanup function. */
export function streamConversation(
  sessionId: string,
  onMessage: (message: A2AMessage) => void,
): () => void {
  const source = new EventSource(`${API}/api/swarm/stream/${sessionId}`)
  source.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data))
    } catch {
      /* keepalive */
    }
  }
  source.onerror = () => source.close()
  return () => source.close()
}

// ------------------------------------------------------------------ tasks
export async function listTasks(sessionId: string) {
  const res = await fetch(`${API}/api/tasks?session_id=${sessionId}`)
  return res.json() as Promise<{ tasks: BoardTask[]; stats: Record<string, unknown> }>
}

export async function createTask(body: Record<string, unknown>) {
  const res = await fetch(`${API}/api/tasks`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  })
  return res.json() as Promise<BoardTask>
}

export async function startTask(id: string) {
  await fetch(`${API}/api/tasks/${id}/start`, { method: "POST" })
}

export async function cancelTask(id: string) {
  await fetch(`${API}/api/tasks/${id}/cancel`, { method: "POST" })
}

export async function deleteTask(id: string) {
  await fetch(`${API}/api/tasks/${id}`, { method: "DELETE" })
}

export async function startAll(sessionId: string) {
  await fetch(`${API}/api/tasks/start-all/${sessionId}`, { method: "POST" })
}

// ----------------------------------------------------------------- models
export async function listModels() {
  const res = await fetch(`${API}/api/models`)
  return res.json()
}

export async function addCustomModel(body: Record<string, unknown>) {
  const res = await fetch(`${API}/api/models/custom`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error((await res.json()).detail ?? "Failed")
  return res.json()
}

export async function deleteCustomModel(alias: string) {
  await fetch(`${API}/api/models/custom/${alias}`, { method: "DELETE" })
}

export async function testModel(model: string) {
  const res = await fetch(`${API}/api/models/test`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ model }),
  })
  return res.json()
}
