"use client"

import { useEffect, useState } from "react"
import { getJSON } from "@/lib/api"
import { useStore } from "@/lib/store"

type Info = {
  providers: string[]
  models: Record<string, string>
  tools: number
  sandbox: string
  max_parallel_agents: number
}

const PROFILES = ["general", "coder", "researcher", "operator", "reviewer"]

export default function Sidebar() {
  const [info, setInfo] = useState<Info | null>(null)
  const { profile, setProfile, mode, setMode, sessionId, reset, agents } = useStore()

  useEffect(() => {
    getJSON<Info>("/api/info")
      .then(setInfo)
      .catch(() => setInfo(null))
  }, [])

  return (
    <aside className="flex w-64 shrink-0 flex-col gap-4 border-r border-edge bg-panel/60 p-4">
      <div>
        <h1 className="text-lg font-semibold text-accent">Bhati AI v2</h1>
        <p className="text-xs text-slate-500">autonomous agent platform</p>
      </div>

      <div className="space-y-2">
        <p className="chip">mode</p>
        <div className="flex gap-2">
          {(["chat", "autonomous"] as const).map((value) => (
            <button
              key={value}
              onClick={() => setMode(value)}
              className={`btn flex-1 ${mode === value ? "border-accent text-accent" : ""}`}
            >
              {value === "chat" ? "Chat" : "Auto"}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <p className="chip">agent profile</p>
        <select
          value={profile}
          onChange={(event) => setProfile(event.target.value)}
          className="w-full rounded-lg border border-edge bg-ink px-2 py-1.5 text-sm"
        >
          {PROFILES.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1">
        <p className="chip">live agents</p>
        {Object.keys(agents).length === 0 && <p className="text-xs text-slate-600">idle</p>}
        {Object.entries(agents).map(([id, status]) => (
          <div key={id} className="flex items-center justify-between text-xs">
            <span className="truncate text-slate-300">{id}</span>
            <span className={status === "running" ? "text-accent" : "text-slate-500"}>{status}</span>
          </div>
        ))}
      </div>

      <div className="mt-auto space-y-1 text-xs text-slate-500">
        <p>session: {sessionId.slice(0, 8)}</p>
        {info && (
          <>
            <p>tools: {info.tools}</p>
            <p>sandbox: {info.sandbox}</p>
            <p>parallel: {info.max_parallel_agents}</p>
            <p className="truncate">providers: {info.providers.join(", ") || "none"}</p>
          </>
        )}
        <button onClick={reset} className="btn mt-2 w-full">
          New session
        </button>
      </div>
    </aside>
  )
}
