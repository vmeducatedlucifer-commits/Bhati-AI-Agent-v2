"use client"

import type { BoardEntry } from "@/lib/swarm"

const KIND_BADGE: Record<string, string> = {
  fact: "bg-zinc-700",
  artifact: "bg-sky-700",
  question: "bg-amber-700",
  decision: "bg-emerald-700",
  risk: "bg-red-700",
  metric: "bg-violet-700",
}

export function BlackboardPanel({ entries }: { entries: BoardEntry[] }) {
  return (
    <div className="h-full space-y-2 overflow-y-auto pr-1">
      {entries.map((entry) => (
        <div key={entry.id} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-2">
          <div className="flex items-center gap-2 text-xs">
            <span className={`rounded px-1.5 py-0.5 text-[10px] uppercase ${KIND_BADGE[entry.kind] ?? "bg-zinc-700"}`}>
              {entry.kind}
            </span>
            <span className="truncate font-medium text-zinc-200">{entry.key}</span>
            <span className="ml-auto text-[10px] text-zinc-500">
              v{entry.version} · {entry.author}
            </span>
          </div>
          <p className="mt-1 line-clamp-4 whitespace-pre-wrap text-xs text-zinc-400">
            {String(entry.value)}
          </p>
        </div>
      ))}
      {entries.length === 0 && <p className="text-sm text-zinc-500">Blackboard is empty.</p>}
    </div>
  )
}
