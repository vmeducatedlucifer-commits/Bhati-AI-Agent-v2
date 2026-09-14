"use client"

import { useStore } from "@/lib/store"

const STATUS_COLOR: Record<string, string> = {
  pending: "text-slate-500 border-edge",
  running: "text-accent border-accent",
  done: "text-emerald-400 border-emerald-700",
  failed: "text-red-400 border-red-700",
  skipped: "text-slate-600 border-edge",
}

export default function PlanGraph() {
  const tasks = useStore((state) => state.tasks)

  if (tasks.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        No plan yet. Run a goal in Auto mode to see the parallel task graph.
      </p>
    )
  }

  const depth = (id: string, seen = new Set<string>()): number => {
    const task = tasks.find((item) => item.id === id)
    if (!task || task.depends_on.length === 0 || seen.has(id)) return 0
    seen.add(id)
    return 1 + Math.max(...task.depends_on.map((dep) => depth(dep, seen)))
  }

  const levels: Record<number, typeof tasks> = {}
  tasks.forEach((task) => {
    const level = depth(task.id)
    levels[level] = [...(levels[level] ?? []), task]
  })

  return (
    <div className="space-y-6">
      {Object.entries(levels).map(([level, group]) => (
        <div key={level}>
          <p className="chip mb-2">wave {Number(level) + 1}</p>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {group.map((task) => (
              <div key={task.id} className={`panel border p-3 ${STATUS_COLOR[task.status] ?? ""}`}>
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-wide">{task.agent}</span>
                  <span className="text-[11px]">{task.status}</span>
                </div>
                <p className="mt-1 text-sm text-slate-200">{task.title}</p>
                {task.depends_on.length > 0 && (
                  <p className="mt-1 text-[11px] text-slate-500">after: {task.depends_on.join(", ")}</p>
                )}
                {task.result && (
                  <p className="mt-2 text-[11px] text-slate-400">{task.result.slice(0, 320)}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
