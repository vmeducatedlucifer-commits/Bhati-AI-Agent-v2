"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { AgentGraph } from "@/components/swarm/AgentGraph"
import { AgentGrid } from "@/components/swarm/AgentGrid"
import { BlackboardPanel } from "@/components/swarm/BlackboardPanel"
import { ConversationFeed } from "@/components/swarm/ConversationFeed"
import { Button, Empty, Panel, Stat } from "@/components/ui/Primitives"
import {
  cancelRun,
  getSnapshot,
  launchSwarm,
  runDebate,
  streamConversation,
  type A2AMessage,
  type Snapshot,
} from "@/lib/swarm"
import { workspace } from "@/lib/client"
import { cx } from "@/lib/format"
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

type View = "graph" | "feed" | "split"

export default function SwarmDashboard() {
  const sessionId = useStore((state) => state.sessionId)
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [live, setLive] = useState<A2AMessage[]>([])
  const [goal, setGoal] = useState("")
  const [size, setSize] = useState(24)
  const [model, setModel] = useState("")
  const [selected, setSelected] = useState<string | null>(null)
  const [kind, setKind] = useState<string | null>(null)
  const [view, setView] = useState<View>("split")
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

  const graphPanel = (
    <Panel
      title="Communication graph"
      subtitle="who is talking to whom — animated, live"
      className="min-h-0"
      bodyClassName="p-2"
      actions={
        selected ? (
          <Button className="text-xs" onClick={() => setSelected(null)}>
            clear focus ×
          </Button>
        ) : null
      }
    >
      <div className="h-full min-h-[260px]">
        <AgentGraph sessionId={sessionId} live={live} selected={selected} onSelect={setSelected} />
      </div>
    </Panel>
  )

  const feedPanel = (
    <Panel
      title="Live conversation"
      subtitle={selected ? `focused on ${selected}` : "every agent-to-agent message"}
      className="min-h-0"
      bodyClassName="flex min-h-0 flex-col gap-2 p-3"
      actions={
        <div className="flex max-w-[420px] flex-wrap justify-end gap-1">
          {KINDS.map((item) => (
            <button
              key={item}
              onClick={() => setKind(kind === item ? null : item)}
              className={cx(
                "chip border transition",
                kind === item
                  ? "bg-white text-black"
                  : "text-[rgb(var(--muted))] hover:text-white",
              )}
            >
              {item}
            </button>
          ))}
        </div>
      }
    >
      <div className="min-h-0 flex-1">
        <ConversationFeed messages={messages} filterAgent={selected} filterKind={kind} />
      </div>
    </Panel>
  )

  return (
    <div className="mx-auto flex h-full max-w-[1700px] flex-col gap-4 p-4 lg:p-6">
      {/* Control bar */}
      <Panel title="Swarm control" subtitle="1 – 1200 agents, auto teams, debate on conflict" bodyClassName="p-4">
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            placeholder="Swarm goal — e.g. audit this repo, fix all failing tests and open a PR"
            className="input min-w-[280px] flex-1"
          />
          <label className="flex items-center gap-2 text-xs text-[rgb(var(--muted))]">
            agents
            <input
              type="number"
              min={1}
              max={1200}
              value={size}
              onChange={(event) => setSize(Number(event.target.value))}
              className="input w-24"
            />
          </label>
          <input
            value={model}
            onChange={(event) => setModel(event.target.value)}
            placeholder="model (optional) e.g. custom:my-vllm"
            className="input w-60"
          />
          <Button variant="primary" onClick={onLaunch} disabled={busy}>
            {busy ? "Launching…" : "Launch swarm"}
          </Button>
          {activeRun && (
            <Button variant="danger" onClick={() => cancelRun(activeRun.id).then(refresh)}>
              Stop
            </Button>
          )}
          <Button onClick={() => runDebate(sessionId, goal || "What should we do next?")}>
            Force debate
          </Button>
          <div className="flex overflow-hidden rounded-xl border">
            {(
              [
                ["split", "Split"],
                ["graph", "Graph"],
                ["feed", "Feed"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                onClick={() => setView(value)}
                className={cx(
                  "px-3 py-2 text-xs transition",
                  view === value ? "bg-white text-black" : "text-[rgb(var(--muted))] hover:bg-white/5",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </Panel>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Agents" value={summary?.total ?? 0} />
        <Stat label="Working" value={summary?.active ?? 0} tone="ok" />
        <Stat label="Messages" value={messages.length} tone="warn" />
        <Stat label="Blackboard" value={snapshot?.blackboard.length ?? 0} />
        <Stat label="Tokens" value={summary?.tokens ?? 0} />
        <Stat
          label="Throughput / min"
          value={activeRun?.scheduler?.throughput_per_min ?? 0}
          tone="ok"
        />
      </div>

      {/* Main grid */}
      <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[300px_minmax(0,1fr)_330px]">
        <Panel title="Agent mesh" subtitle="click an agent to focus it" className="min-h-0" bodyClassName="p-3">
          <AgentGrid agents={snapshot?.agents ?? []} onSelect={setSelected} selected={selected} />
        </Panel>

        <div className="grid min-h-0 gap-4">
          {view === "graph" && graphPanel}
          {view === "feed" && feedPanel}
          {view === "split" && (
            <div className="grid min-h-0 grid-rows-2 gap-4">
              {graphPanel}
              {feedPanel}
            </div>
          )}
        </div>

        <div className="flex min-h-0 flex-col gap-4">
          <Panel title="Shared blackboard" className="min-h-0 flex-1" bodyClassName="p-3">
            <BlackboardPanel entries={snapshot?.blackboard ?? []} />
          </Panel>

          <Panel title="Plan" subtitle="task → agent assignment" className="max-h-64" bodyClassName="p-3">
            {activeRun?.plan?.tasks.length ? (
              activeRun.plan.tasks.map((task) => (
                <div key={task.id} className="flex items-center gap-2 py-1 text-xs">
                  <span
                    className={cx(
                      "h-2 w-2 shrink-0 rounded-full",
                      task.status === "done"
                        ? "bg-[rgb(var(--ok))]"
                        : task.status === "running"
                          ? "animate-pulse bg-[rgb(var(--warn))]"
                          : task.status === "failed"
                            ? "bg-[rgb(var(--err))]"
                            : "bg-white/25",
                    )}
                  />
                  <span className="truncate">{task.title}</span>
                  <span className="ml-auto shrink-0 text-[rgb(var(--muted))]">{task.agent}</span>
                </div>
              ))
            ) : (
              <Empty icon="🗺️" text="No active plan. Launch a swarm to see the task graph." />
            )}
          </Panel>

          <Panel title="Agent workspaces" subtitle="every agent writes real files" bodyClassName="flex gap-2 p-3">
            <Link href="/workspace" className="btn btn-ghost flex-1 text-xs">
              Browse files
            </Link>
            <a href={workspace.archiveUrl(sessionId)} download className="btn btn-primary flex-1 text-xs">
              Download .zip
            </a>
          </Panel>
        </div>
      </div>
    </div>
  )
}
