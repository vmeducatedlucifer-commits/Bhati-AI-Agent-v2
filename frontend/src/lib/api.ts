export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export type AgentEvent = {
  type: string
  session_id?: string
  agent_id?: string
  data: Record<string, any>
}

export async function getJSON<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`)
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`)
  return response.json()
}

export async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`)
  return response.json()
}

/** Streams SSE from POST /api/chat/stream and yields parsed events. */
export async function* streamChat(body: Record<string, unknown>): AsyncGenerator<AgentEvent> {
  const response = await fetch(`${API}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!response.body) throw new Error("No stream body")
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split("\n\n")
    buffer = frames.pop() ?? ""
    for (const frame of frames) {
      const lines = frame.split("\n")
      const eventLine = lines.find((line) => line.startsWith("event: "))
      const dataLine = lines.find((line) => line.startsWith("data: "))
      if (!dataLine) continue
      try {
        const parsed = JSON.parse(dataLine.slice(6))
        yield { type: eventLine?.slice(7) ?? "message", ...parsed } as AgentEvent
      } catch {
        /* keepalive frame */
      }
    }
  }
}
