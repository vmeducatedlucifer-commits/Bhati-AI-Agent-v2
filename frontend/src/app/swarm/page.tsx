"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { AgentGrid } from "@/components/swarm/AgentGrid"
import { BlackboardPanel } from "@/components/swarm/BlackboardPanel"
import { ConversationFeed } from "@/components/swarm/ConversationFeed"
import {
  cancelRun,
  getSnapshot,
  launchSwarm,
  runDebate,
  streamConversation,
  type A2AMessage,
  type Snapshot,
} from "@/lib/swarm"
import { useStore } from "@/lib/store"

const KINDS = [
  "proposal",
  "critique",
  "vote",
  "request",
  "handoff",
  "help",
  "result",
  "announce",
  "status",
]

export default function SwarmDashboard() {
  const sessionId = useStore((state) => state.sessionId)
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [live, setLive] = useState<A2AMessage[]>([])
  const [goal, setGoal] = useState("")
  const [size, setSize] = useState(24)
  const [model, setModel] = useState("")
  const [selected, setSelected] = useState<string | null>(null)
  const [kind, setKind] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    setSnapshot(await getSnapshot(sessionId))
  }, [sessionId])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 3000)
    return () => clearInterval(timer)
  }, [refresh])

  useEffect(() => {
    setLive([])
    return streamConversation(sessionId, (message) =>
      setLive((prev) => [...prev.slice(-800), message]),
    )
  }, [sessionId])

  const messages = useMemo(() => {
    const seen = new Set<string>()
    return [...(snapshot?.messages ?? []), ...live].filter((message) => {
      if (seen.has(message.id)) return false
      seen.add(message.id)
      return true
    })
  }, [snapshot?.messages, live])

  const summary = snapshot?.summary
  const activeRun = snapshot?.runs.find((run) => run.status === "running")

  async function onLaunch() {
    if (!goal.trim()) return
    setBusy(true)
    try {
      await launchSwarm({ session_id: sessionId, goal, size, model: model || null })
      setGoal("")
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="flex h-screen flex-col gap-3 bg-zinc-950 p-4 text-zinc-100">
      {/* Control bar */}
      <header className="flex flex-wrap items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/50 p-3">
        <h1 className="mr-2 text-lg font-semibold">Swarm Control</h1>
        <input
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
          placeholder="Swarm goal — e.g. audit this repo, fix all failing tests and open a PR"
          className="min-w-[280px] flex-1 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm outline-none focus:border-zinc-600"
        />
        <label className="flex items-center gap-2 text-xs text-zinc-400">
          agents
          <input
            type="number"
            min={1}
            max={1200}
            value={size}
            onChange={(event) => setSize(Number(event.target.value))}
            className="w-20 rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-2 text-sm"
          />
        </label>
        <input
          value={model}
          onChange={(event) => setModel(event.target.value)}
          placeholder="model (optional, e.g. custom:my-vllm)"
          className="w-56 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
        />
        <button
          onClick={onLaunch}
          disabled={busy}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
        >
          {busy ? "Launching…" : "Launch swarm"}
        </button>
        {activeRun && (
          <button
            onClick={() => cancelRun(activeRun.id).then(refresh)}
            className="rounded-lg bg-red-700 px-3 py-2 text-sm hover:bg-red-600"
          >
            Stop
          </button>
        )}
        <button
          onClick={() => runDebate(sessionId, goal || "What should we do next?")}
          className="rounded-lg border border-zinc-700 px-3 py-2 text-sm hover:border-zinc-500"
        >
          Force debate
        </button>
      </header>

      {/* Stats */}
      <section className="grid grid-cols-2 gap-3 md:grid-cols-6">
        {[
          ["Agents", summary?.total ?? 0],
          ["Working", summary?.active ?? 0],
          ["Messages", messages.length],
          ["Blackboard", snapshot?.blackboard.length ?? 0],
          ["Tokens", summary?.tokens ?? 0],
          ["Throughput/min", activeRun?.scheduler?.throughput_per_min ?? 0],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-3">
            <div className="text-xs uppercase tracking-wide text-zinc-500">{label}</div>
            <div className="text-xl font-semibold">{String(value)}</div>
          </div>
        ))}
      </section>

      {/* Main grid */}
      <section className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-[320px_1fr_320px]">
        <div className="min-h-0 overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900/40 p-3">
          <h2 className="mb-2 text-sm font-semibold">Agent mesh</h2>
          <AgentGrid agents={snapshot?.agents ?? []} onSelect={setSelected} selected={selected} />
        </div>

        <div className="flex min-h-0 flex-col rounded-xl border border-zinc-800 bg-zinc-900/40 p-3">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold">Live conversation</h2>
            {selected && (
              <span className="rounded bg-zinc-800 px-2 py-0.5 text-xs">
                {selected}
                <button className="ml-2 text-zinc-500" onClick={() => setSelected(null)}>
                  ×
                </button>
              </span>
            )}
            <div className="ml-auto flex flex-wrap gap-1">
              {KINDS.map((item) => (
                <button
                  key={item}
                  onClick={() => setKind(kind === item ? null : item)}
                  className={`rounded px-2 py-0.5 text-[10px] uppercase ${
                    kind === item ? "bg-white text-black" : "bg-zinc-800 text-zinc-400"
                  }`}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
          <div className="min-h-0 flex-1">
            <ConversationFeed messages={messages} filterAgent={selected} filterKind={kind} />
          </div>
        </div>

        <div className="flex min-h-0 flex-col gap-3">
          <div className="min-h-0 flex-1 rounded-xl border border-zinc-800 bg-zinc-900/40 p-3">
            <h2 className="mb-2 text-sm font-semibold">Shared blackboard</h2>
            <BlackboardPanel entries={snapshot?.blackboard ?? []} />
          </div>
          <div className="max-h-64 overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900/40 p-3">
            <h2 className="mb-2 text-sm font-semibold">Plan</h2>
            {activeRun?.plan?.tasks.map((task) => (
              <div key={task.id} className="flex items-center gap-2 py-1 text-xs">
                <span
                  className={`h-2 w-2 rounded-full ${
                    task.status === "done"
                      ? "bg-emerald-500"
                      : task.status === "running"
                        ? "animate-pulse bg-amber-500"
                        : task.status === "failed"
                          ? "bg-red-500"
                          : "bg-zinc-600"
                  }`}
                />
                <span className="truncate">{task.title}</span>
                <span className="ml-auto text-zinc-600">{task.agent}</span>
              </div>
            )) ?? <p className="text-sm text-zinc-500">No active plan.</p>}
          </div>
        </div>
      </section>
    </main>
  )
}
