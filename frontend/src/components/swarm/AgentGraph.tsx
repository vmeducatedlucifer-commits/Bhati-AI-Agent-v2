"use client"

/**
 * Agent-to-agent communication graph.
 *
 * Canvas-rendered force-directed layout (no extra deps) where every edge is a
 * real conversation between two agents. Animated particles travel along each
 * edge in the direction the message flowed. Live SSE messages fire an instant
 * pulse; the weighted graph from the backend keeps the layout stable.
 *
 * Every payload is normalized before it touches the render loop — a backend
 * error response must never crash the dashboard.
 */

import { useEffect, useMemo, useRef, useState } from "react"
import { API } from "@/lib/api"
import type { A2AMessage } from "@/lib/swarm"

const CLUSTER_LIMIT = 260

export type GraphNode = {
  id: string
  label: string
  type: "queen" | "lead" | "agent" | "topic"
  team: string
  role: string
  status: string
  sent: number
  received: number
  degree: number
  steps?: number
  tokens?: number
  current_action?: string
}

export type GraphEdge = {
  id: string
  source: string
  target: string
  count: number
  kinds: Record<string, number>
  last_kind: string
  last_message: string
  broadcast: boolean
}

export type GraphStats = {
  node_count: number
  edge_count: number
  message_count: number
  density: number
  hubs: { id: string; degree: number }[]
  isolated: string[]
}

export type GraphPayload = {
  nodes: GraphNode[]
  edges: GraphEdge[]
  stats: GraphStats
}

const EMPTY_GRAPH: GraphPayload = {
  nodes: [],
  edges: [],
  stats: {
    node_count: 0,
    edge_count: 0,
    message_count: 0,
    density: 0,
    hubs: [],
    isolated: [],
  },
}

/** Coerce anything the API returns into a render-safe graph. */
function normalizeGraph(raw: unknown): GraphPayload {
  if (!raw || typeof raw !== "object") return EMPTY_GRAPH
  const data = raw as Record<string, unknown>
  const stats = (data.stats ?? {}) as Record<string, unknown>

  const nodes = (Array.isArray(data.nodes) ? (data.nodes as GraphNode[]) : [])
    .filter((node) => node && typeof node.id === "string")
    .map((node) => ({
      ...node,
      label: node.label ?? node.id,
      type: (node.type ?? "agent") as GraphNode["type"],
      team: node.team ?? "core",
      role: node.role ?? "agent",
      status: node.status ?? "idle",
      sent: Number(node.sent ?? 0),
      received: Number(node.received ?? 0),
      degree: Number(node.degree ?? 0),
    }))

  const ids = new Set(nodes.map((node) => node.id))
  const edges = (Array.isArray(data.edges) ? (data.edges as GraphEdge[]) : [])
    .filter(
      (edge) =>
        edge &&
        typeof edge.source === "string" &&
        typeof edge.target === "string" &&
        ids.has(edge.source) &&
        ids.has(edge.target),
    )
    .map((edge) => ({
      ...edge,
      id: edge.id ?? `${edge.source}->${edge.target}`,
      count: Number(edge.count ?? 1),
      kinds: edge.kinds ?? {},
      last_kind: edge.last_kind ?? "chat",
      last_message: edge.last_message ?? "",
      broadcast: Boolean(edge.broadcast),
    }))

  return {
    nodes,
    edges,
    stats: {
      node_count: Number(stats.node_count ?? nodes.length),
      edge_count: Number(stats.edge_count ?? edges.length),
      message_count: Number(stats.message_count ?? 0),
      density: Number(stats.density ?? 0),
      hubs: Array.isArray(stats.hubs) ? (stats.hubs as GraphStats["hubs"]) : [],
      isolated: Array.isArray(stats.isolated) ? (stats.isolated as string[]) : [],
    },
  }
}

const KIND_COLOR: Record<string, string> = {
  proposal: "#38bdf8",
  critique: "#fb923c",
  vote: "#a78bfa",
  request: "#facc15",
  response: "#4ade80",
  handoff: "#f472b6",
  help: "#f87171",
  result: "#34d399",
  announce: "#94a3b8",
  status: "#64748b",
  chat: "#e2e8f0",
}

const STATUS_COLOR: Record<string, string> = {
  working: "#34d399",
  waiting: "#facc15",
  blocked: "#fb923c",
  failed: "#f87171",
  done: "#38bdf8",
  idle: "#475569",
}

type Body = {
  id: string
  node: GraphNode
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  pulse: number
}

type Particle = {
  from: string
  to: string
  progress: number
  speed: number
  color: string
}

function clusterKey(node: GraphNode): string {
  if (node.type === "queen") return "queen"
  if (node.type === "topic") return node.id
  if (node.type === "lead") return node.id
  return `cluster:${node.team}`
}

/** Collapse a huge roster into team hubs so the canvas stays readable. */
function clusterGraph(graph: GraphPayload): GraphPayload {
  if (graph.nodes.length <= CLUSTER_LIMIT) return graph

  const mapping = new Map<string, string>()
  const nodes = new Map<string, GraphNode>()

  for (const node of graph.nodes) {
    const key = clusterKey(node)
    mapping.set(node.id, key)
    const existing = nodes.get(key)
    if (!existing) {
      nodes.set(key, {
        ...node,
        id: key,
        label: key.startsWith("cluster:") ? `${node.team} ×1` : node.label,
      })
      continue
    }
    existing.degree += node.degree
    existing.sent += node.sent
    existing.received += node.received
    if (key.startsWith("cluster:")) {
      const count = Number(existing.label.split("×")[1] ?? 1) + 1
      existing.label = `${existing.team} ×${count}`
      if (node.status === "working") existing.status = "working"
    }
  }

  const edges = new Map<string, GraphEdge>()
  for (const edge of graph.edges) {
    const source = mapping.get(edge.source) ?? edge.source
    const target = mapping.get(edge.target) ?? edge.target
    if (source === target) continue
    const id = `${source}->${target}`
    const existing = edges.get(id)
    if (existing) {
      existing.count += edge.count
      existing.last_kind = edge.last_kind
    } else {
      edges.set(id, { ...edge, id, source, target })
    }
  }

  return { ...graph, nodes: [...nodes.values()], edges: [...edges.values()] }
}

export function AgentGraph({
  sessionId,
  live,
  onSelect,
  selected,
}: {
  sessionId: string
  live: A2AMessage[]
  onSelect?: (id: string | null) => void
  selected?: string | null
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const bodiesRef = useRef<Map<string, Body>>(new Map())
  const particlesRef = useRef<Particle[]>([])
  const hoverRef = useRef<Body | null>(null)
  const graphRef = useRef<GraphPayload | null>(null)
  const seenRef = useRef<Set<string>>(new Set())

  const [graph, setGraph] = useState<GraphPayload>(EMPTY_GRAPH)
  const [hover, setHover] = useState<GraphNode | null>(null)
  const [windowSeconds, setWindowSeconds] = useState(0)
  const [showBroadcasts, setShowBroadcasts] = useState(true)

  const view = useMemo(() => {
    try {
      return clusterGraph(graph)
    } catch {
      return EMPTY_GRAPH
    }
  }, [graph])

  // ---- data ---------------------------------------------------------------
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const response = await fetch(
          `${API}/api/swarm/graph/${sessionId}?window=${windowSeconds}&include_broadcasts=${showBroadcasts}`,
        )
        if (!response.ok) return
        const payload = normalizeGraph(await response.json())
        if (!cancelled) setGraph(payload)
      } catch {
        /* dashboard keeps last known graph */
      }
    }
    load()
    const timer = setInterval(load, 2500)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [sessionId, windowSeconds, showBroadcasts])

  useEffect(() => {
    graphRef.current = view
  }, [view])

  // ---- live pulses --------------------------------------------------------
  useEffect(() => {
    const bodies = bodiesRef.current
    for (const message of (live ?? []).slice(-40)) {
      if (!message || seenRef.current.has(message.id)) continue
      seenRef.current.add(message.id)
      const from = bodies.get(message.sender)
      const target = message.recipient === "*" ? `topic:${message.topic}` : message.recipient
      const to = bodies.get(target)
      if (from) from.pulse = 1
      if (to) to.pulse = 1
      if (from && to) {
        particlesRef.current.push({
          from: from.id,
          to: to.id,
          progress: 0,
          speed: 0.02,
          color: KIND_COLOR[message.kind] ?? "#e2e8f0",
        })
      }
    }
    if (seenRef.current.size > 4000) seenRef.current = new Set()
  }, [live])

  // ---- simulation + render loop ------------------------------------------
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext("2d")
    if (!context) return

    let frame = 0
    let tick = 0

    function resize() {
      const ratio = window.devicePixelRatio || 1
      const rect = canvas!.getBoundingClientRect()
      canvas!.width = Math.max(1, rect.width * ratio)
      canvas!.height = Math.max(1, rect.height * ratio)
      context!.setTransform(ratio, 0, 0, ratio, 0, 0)
    }
    resize()
    window.addEventListener("resize", resize)

    function syncBodies(payload: GraphPayload, width: number, height: number) {
      const bodies = bodiesRef.current
      const ids = new Set(payload.nodes.map((node) => node.id))
      for (const id of [...bodies.keys()]) if (!ids.has(id)) bodies.delete(id)

      payload.nodes.forEach((node, index) => {
        const existing = bodies.get(node.id)
        if (existing) {
          existing.node = node
          existing.radius =
            node.type === "queen"
              ? 14
              : node.type === "lead"
                ? 10
                : node.type === "topic"
                  ? 8
                  : 4 + Math.min(6, Math.log2(1 + node.degree))
          return
        }
        const angle = (index / Math.max(1, payload.nodes.length)) * Math.PI * 2
        const ring =
          node.type === "queen"
            ? 0
            : node.type === "lead"
              ? 0.28
              : node.type === "topic"
                ? 0.18
                : 0.42
        bodies.set(node.id, {
          id: node.id,
          node,
          x: width / 2 + Math.cos(angle) * width * ring,
          y: height / 2 + Math.sin(angle) * height * ring,
          vx: 0,
          vy: 0,
          radius: node.type === "queen" ? 14 : node.type === "lead" ? 10 : 5,
          pulse: 0,
        })
      })
    }

    function simulate(payload: GraphPayload, width: number, height: number) {
      const bodies = [...bodiesRef.current.values()]
      if (!bodies.length) return
      const centerX = width / 2
      const centerY = height / 2

      const sample = bodies.length > 160 ? 40 : bodies.length
      for (const body of bodies) {
        for (let index = 0; index < sample; index += 1) {
          const other = bodies[Math.floor(Math.random() * bodies.length)]
          if (!other || other === body) continue
          const dx = body.x - other.x
          const dy = body.y - other.y
          const distanceSq = dx * dx + dy * dy || 0.01
          if (distanceSq > 40000) continue
          const force = 420 / distanceSq
          body.vx += dx * force
          body.vy += dy * force
        }
        body.vx += (centerX - body.x) * 0.0016
        body.vy += (centerY - body.y) * 0.0016
      }

      for (const edge of payload.edges) {
        const source = bodiesRef.current.get(edge.source)
        const target = bodiesRef.current.get(edge.target)
        if (!source || !target) continue
        const dx = target.x - source.x
        const dy = target.y - source.y
        const distance = Math.hypot(dx, dy) || 0.01
        const rest = 120
        const strength = Math.min(0.02, 0.004 + edge.count * 0.0008)
        const force = ((distance - rest) / distance) * strength
        source.vx += dx * force
        source.vy += dy * force
        target.vx -= dx * force
        target.vy -= dy * force
      }

      for (const body of bodies) {
        body.vx *= 0.86
        body.vy *= 0.86
        body.x = Math.max(body.radius + 4, Math.min(width - body.radius - 4, body.x + body.vx))
        body.y = Math.max(body.radius + 4, Math.min(height - body.radius - 4, body.y + body.vy))
        body.pulse *= 0.94
      }
    }

    function draw() {
      frame = requestAnimationFrame(draw)
      tick += 1
      const payload = graphRef.current
      const rect = canvas!.getBoundingClientRect()
      const width = rect.width
      const height = rect.height

      context!.clearRect(0, 0, width, height)
      if (!payload || !payload.nodes.length) return

      try {
        syncBodies(payload, width, height)
        if (tick % 2 === 0) simulate(payload, width, height)
      } catch {
        return
      }

      const bodies = bodiesRef.current
      const focus = selected ?? hoverRef.current?.id ?? null
      const maxCount = Math.max(1, ...payload.edges.map((edge) => edge.count), 1)

      // edges
      for (const edge of payload.edges) {
        const source = bodies.get(edge.source)
        const target = bodies.get(edge.target)
        if (!source || !target) continue
        const dimmed = focus !== null && edge.source !== focus && edge.target !== focus
        context!.globalAlpha = dimmed ? 0.06 : 0.34 + 0.4 * (edge.count / maxCount)
        context!.strokeStyle = KIND_COLOR[edge.last_kind] ?? "#475569"
        context!.lineWidth = Math.min(4, 0.6 + Math.log2(1 + edge.count))
        context!.beginPath()
        context!.moveTo(source.x, source.y)
        const midX = (source.x + target.x) / 2 + (target.y - source.y) * 0.08
        const midY = (source.y + target.y) / 2 - (target.x - source.x) * 0.08
        context!.quadraticCurveTo(midX, midY, target.x, target.y)
        context!.stroke()

        if (!dimmed) {
          const density = Math.min(3, Math.ceil(edge.count / 4))
          for (let index = 0; index < density; index += 1) {
            const progress = (tick * 0.006 + index / density + edge.count * 0.01) % 1
            const inverse = 1 - progress
            const x =
              inverse * inverse * source.x +
              2 * inverse * progress * midX +
              progress * progress * target.x
            const y =
              inverse * inverse * source.y +
              2 * inverse * progress * midY +
              progress * progress * target.y
            context!.globalAlpha = 0.8
            context!.fillStyle = KIND_COLOR[edge.last_kind] ?? "#94a3b8"
            context!.beginPath()
            context!.arc(x, y, 1.6, 0, Math.PI * 2)
            context!.fill()
          }
        }
      }

      // live message pulses
      particlesRef.current = particlesRef.current.filter((particle) => particle.progress < 1)
      for (const particle of particlesRef.current) {
        const source = bodies.get(particle.from)
        const target = bodies.get(particle.to)
        if (!source || !target) continue
        particle.progress += particle.speed
        const progress = particle.progress
        const x = source.x + (target.x - source.x) * progress
        const y = source.y + (target.y - source.y) * progress
        context!.globalAlpha = 1
        context!.fillStyle = particle.color
        context!.shadowBlur = 12
        context!.shadowColor = particle.color
        context!.beginPath()
        context!.arc(x, y, 3.2, 0, Math.PI * 2)
        context!.fill()
        context!.shadowBlur = 0
      }

      // nodes
      for (const body of bodies.values()) {
        const dimmed = focus !== null && body.id !== focus
        const color =
          body.node.type === "topic" ? "#6366f1" : (STATUS_COLOR[body.node.status] ?? "#475569")
        context!.globalAlpha = dimmed ? 0.25 : 1

        if (body.pulse > 0.05) {
          context!.beginPath()
          context!.arc(body.x, body.y, body.radius + body.pulse * 14, 0, Math.PI * 2)
          context!.strokeStyle = color
          context!.globalAlpha = body.pulse * 0.5
          context!.lineWidth = 1.5
          context!.stroke()
          context!.globalAlpha = dimmed ? 0.25 : 1
        }

        context!.beginPath()
        context!.arc(body.x, body.y, body.radius, 0, Math.PI * 2)
        context!.fillStyle = color
        context!.fill()
        if (body.node.type !== "agent") {
          context!.strokeStyle = "#0f172a"
          context!.lineWidth = 2
          context!.stroke()
          context!.fillStyle = "#e2e8f0"
          context!.font = "10px ui-sans-serif, system-ui"
          context!.textAlign = "center"
          context!.fillText(body.node.label, body.x, body.y - body.radius - 5)
        }
      }
      context!.globalAlpha = 1
    }

    frame = requestAnimationFrame(draw)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener("resize", resize)
    }
  }, [selected])

  // ---- pointer interaction ------------------------------------------------
  function pick(event: React.MouseEvent<HTMLCanvasElement>): Body | null {
    const rect = event.currentTarget.getBoundingClientRect()
    const x = event.clientX - rect.left
    const y = event.clientY - rect.top
    let best: Body | null = null
    let bestDistance = 18
    for (const body of bodiesRef.current.values()) {
      const distance = Math.hypot(body.x - x, body.y - y)
      if (distance < bestDistance) {
        bestDistance = distance
        best = body
      }
    }
    return best
  }

  const hubs = view.stats.hubs ?? []

  return (
    <div className="relative h-full w-full">
      <canvas
        ref={canvasRef}
        className="h-full w-full cursor-crosshair rounded-xl bg-black/50"
        onMouseMove={(event) => {
          const body = pick(event)
          hoverRef.current = body
          setHover(body?.node ?? null)
        }}
        onMouseLeave={() => {
          hoverRef.current = null
          setHover(null)
        }}
        onClick={(event) => {
          const body = pick(event)
          onSelect?.(body && body.id !== selected ? body.id : null)
        }}
      />

      {!view.nodes.length && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-xs text-[rgb(var(--muted))]">
          No agent traffic yet — launch a swarm to see the live mesh.
        </div>
      )}

      {/* controls */}
      <div className="absolute left-2 top-2 flex flex-wrap items-center gap-1.5 text-[11px]">
        {(
          [
            [0, "all"],
            [60, "1m"],
            [300, "5m"],
            [900, "15m"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={label}
            onClick={() => setWindowSeconds(value)}
            className={`rounded-lg border px-2 py-0.5 ${
              windowSeconds === value ? "bg-white text-black" : "bg-black/50 text-[rgb(var(--muted))]"
            }`}
          >
            {label}
          </button>
        ))}
        <button
          onClick={() => setShowBroadcasts((previous) => !previous)}
          className={`rounded-lg border px-2 py-0.5 ${
            showBroadcasts
              ? "bg-[rgb(var(--accent))]/70 text-white"
              : "bg-black/50 text-[rgb(var(--muted))]"
          }`}
        >
          broadcasts
        </button>
      </div>

      {/* legend */}
      <div className="absolute right-2 top-2 flex flex-wrap justify-end gap-1 text-[10px]">
        {Object.entries(KIND_COLOR)
          .slice(0, 7)
          .map(([kind, color]) => (
            <span
              key={kind}
              className="flex items-center gap-1 rounded-lg border bg-black/60 px-1.5 py-0.5"
            >
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
              {kind}
            </span>
          ))}
      </div>

      {/* stats + hubs */}
      <div className="absolute bottom-2 left-2 rounded-xl border bg-black/70 px-3 py-2 text-[11px] text-[rgb(var(--muted))]">
        <div>
          {view.stats.node_count} nodes · {view.stats.edge_count} links ·{" "}
          {view.stats.message_count} msgs
          {graph.nodes.length > CLUSTER_LIMIT && (
            <span className="ml-2 text-[rgb(var(--warn))]">clustered by team</span>
          )}
        </div>
        {hubs.length > 0 && (
          <div className="mt-1 truncate">
            top talkers: {hubs.slice(0, 3).map((hub) => `${hub.id} (${hub.degree})`).join(", ")}
          </div>
        )}
      </div>

      {/* hover card */}
      {hover && (
        <div className="pointer-events-none absolute bottom-2 right-2 w-64 rounded-xl border bg-black/90 p-3 text-xs">
          <div className="font-semibold">{hover.label}</div>
          <div className="text-[rgb(var(--muted))]">
            {hover.role} · {hover.team} · {hover.status}
          </div>
          <div className="mt-1 text-[rgb(var(--muted))]">
            sent {hover.sent} · received {hover.received}
            {hover.steps ? ` · ${hover.steps} steps` : ""}
          </div>
          {hover.current_action && <div className="mt-1 line-clamp-3">{hover.current_action}</div>}
        </div>
      )}
    </div>
  )
}

export default AgentGraph
