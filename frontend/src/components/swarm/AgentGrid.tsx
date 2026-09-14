"use client"

import type { AgentRecord } from "@/lib/swarm"

const STATUS_COLOR: Record<string, string> = {
  working: "bg-emerald-500",
  idle: "bg-zinc-600",
  waiting: "bg-amber-500",
  blocked: "bg-orange-600",
  done: "bg-sky-500",
  failed: "bg-red-500",
}

/** Scales from 5 to 1200 agents: dense dot-grid + hover detail. */
export function AgentGrid({
  agents,
  onSelect,
  selected,
}: {
  agents: AgentRecord[]
  onSelect: (id: string | null) => void
  selected: string | null
}) {
  const teams = Array.from(new Set(agents.map((a) => a.team)))
  const dense = agents.length > 60

  return (
    <div className="space-y-4">
      {teams.map((team) => {
        const members = agents.filter((a) => a.team === team)
        return (
          <div key={team}>
            <div className="mb-1 flex items-center justify-between text-xs text-zinc-400">
              <span className="font-medium uppercase tracking-wide">{team}</span>
              <span>
                {members.filter((m) => m.status === "working").length}/{members.length} active
              </span>
            </div>
            <div className={dense ? "flex flex-wrap gap-1" : "grid grid-cols-2 gap-2 md:grid-cols-3"}>
              {members.map((agent) =>
                dense ? (
                  <button
                    key={agent.id}
                    title={`${agent.id} (${agent.role}) - ${agent.status}\n${agent.current_action}`}
                    onClick={() => onSelect(agent.id === selected ? null : agent.id)}
                    className={`h-3 w-3 rounded-sm ${STATUS_COLOR[agent.status] ?? "bg-zinc-700"} ${
                      selected === agent.id ? "ring-2 ring-white" : ""
                    }`}
                  />
                ) : (
                  <button
                    key={agent.id}
                    onClick={() => onSelect(agent.id === selected ? null : agent.id)}
                    className={`rounded-lg border border-zinc-800 bg-zinc-900/60 p-2 text-left transition hover:border-zinc-600 ${
                      selected === agent.id ? "border-white" : ""
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={`h-2 w-2 rounded-full ${STATUS_COLOR[agent.status] ?? "bg-zinc-700"} ${
                          agent.status === "working" ? "animate-pulse" : ""
                        }`}
                      />
                      <span className="truncate text-sm font-medium">{agent.id}</span>
                    </div>
                    <div className="mt-1 truncate text-xs text-zinc-500">
                      {agent.role} · {agent.steps} steps · {agent.tokens} tok
                    </div>
                    {agent.current_action && (
                      <div className="mt-1 truncate text-xs text-zinc-400">{agent.current_action}</div>
                    )}
                  </button>
                ),
              )}
            </div>
          </div>
        )
      })}
      {agents.length === 0 && (
        <p className="text-sm text-zinc-500">No agents yet. Launch a swarm to populate the mesh.</p>
      )}
    </div>
  )
}
