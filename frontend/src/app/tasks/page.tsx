"use client"

import { useCallback, useEffect, useState } from "react"
import {
  cancelTask,
  createTask,
  deleteTask,
  listTasks,
  startAll,
  startTask,
  type BoardTask,
} from "@/lib/swarm"
import { useStore } from "@/lib/store"

const COLUMNS = [
  { key: "queued", label: "Queued" },
  { key: "running", label: "Running" },
  { key: "review", label: "Review" },
  { key: "done", label: "Done" },
  { key: "failed", label: "Failed / Cancelled" },
]

function column(task: BoardTask) {
  if (["queued", "assigned", "blocked"].includes(task.status)) return "queued"
  if (task.status === "running") return "running"
  if (task.status === "review") return "review"
  if (task.status === "done") return "done"
  return "failed"
}

export default function TaskPanel() {
  const sessionId = useStore((state) => state.sessionId)
  const [tasks, setTasks] = useState<BoardTask[]>([])
  const [open, setOpen] = useState<BoardTask | null>(null)
  const [form, setForm] = useState({
    title: "",
    description: "",
    acceptance: "",
    priority: 5,
    assignee: "auto",
    mode: "swarm",
    size: 12,
    model: "",
  })

  const refresh = useCallback(async () => {
    const data = await listTasks(sessionId)
    setTasks(data.tasks ?? [])
  }, [sessionId])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 2500)
    return () => clearInterval(timer)
  }, [refresh])

  async function submit() {
    if (!form.title.trim()) return
    await createTask({
      session_id: sessionId,
      ...form,
      model: form.model || null,
      size: form.mode === "swarm" ? form.size : null,
      autostart: true,
    })
    setForm({ ...form, title: "", description: "", acceptance: "" })
    refresh()
  }

  return (
    <main className="flex h-screen flex-col gap-3 bg-zinc-950 p-4 text-zinc-100">
      <header className="flex items-center gap-3">
        <h1 className="text-lg font-semibold">Task Panel</h1>
        <span className="text-xs text-zinc-500">
          Assign work here — the swarm must complete it.
        </span>
        <button
          onClick={() => startAll(sessionId).then(refresh)}
          className="ml-auto rounded-lg border border-zinc-700 px-3 py-1.5 text-sm hover:border-zinc-500"
        >
          Start all queued
        </button>
      </header>

      {/* Composer */}
      <section className="grid gap-2 rounded-xl border border-zinc-800 bg-zinc-900/50 p-3 md:grid-cols-[2fr_1fr]">
        <div className="space-y-2">
          <input
            value={form.title}
            onChange={(event) => setForm({ ...form, title: event.target.value })}
            placeholder="Task title — what must be done"
            className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm outline-none focus:border-zinc-600"
          />
          <textarea
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
            placeholder="Details, constraints, links, repo paths…"
            rows={3}
            className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm outline-none focus:border-zinc-600"
          />
          <input
            value={form.acceptance}
            onChange={(event) => setForm({ ...form, acceptance: event.target.value })}
            placeholder="Acceptance criteria — how we know it's truly done"
            className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm outline-none focus:border-zinc-600"
          />
        </div>
        <div className="space-y-2 text-sm">
          <div className="flex gap-2">
            <select
              value={form.mode}
              onChange={(event) => setForm({ ...form, mode: event.target.value })}
              className="flex-1 rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-2"
            >
              <option value="swarm">Swarm</option>
              <option value="single">Single agent</option>
            </select>
            <input
              type="number"
              min={1}
              max={1200}
              value={form.size}
              onChange={(event) => setForm({ ...form, size: Number(event.target.value) })}
              className="w-24 rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-2"
            />
          </div>
          <select
            value={form.assignee}
            onChange={(event) => setForm({ ...form, assignee: event.target.value })}
            className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-2"
          >
            {["auto", "coder", "researcher", "operator", "reviewer", "planner", "general"].map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
          <div className="flex gap-2">
            <input
              type="number"
              min={1}
              max={10}
              value={form.priority}
              onChange={(event) => setForm({ ...form, priority: Number(event.target.value) })}
              className="w-20 rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-2"
              title="Priority (1 = highest)"
            />
            <input
              value={form.model}
              onChange={(event) => setForm({ ...form, model: event.target.value })}
              placeholder="model override"
              className="flex-1 rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-2"
            />
          </div>
          <button
            onClick={submit}
            className="w-full rounded-lg bg-emerald-600 px-3 py-2 font-medium hover:bg-emerald-500"
          >
            Assign to swarm
          </button>
        </div>
      </section>

      {/* Board */}
      <section className="grid min-h-0 flex-1 grid-cols-1 gap-3 md:grid-cols-5">
        {COLUMNS.map((col) => (
          <div
            key={col.key}
            className="flex min-h-0 flex-col rounded-xl border border-zinc-800 bg-zinc-900/40 p-2"
          >
            <h2 className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-zinc-400">
              {col.label} ({tasks.filter((task) => column(task) === col.key).length})
            </h2>
            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto">
              {tasks
                .filter((task) => column(task) === col.key)
                .map((task) => (
                  <div
                    key={task.id}
                    onClick={() => setOpen(task)}
                    className="cursor-pointer rounded-lg border border-zinc-800 bg-zinc-950/60 p-2 hover:border-zinc-600"
                  >
                    <div className="flex items-start gap-2">
                      <span className="rounded bg-zinc-800 px-1.5 text-[10px]">P{task.priority}</span>
                      <span className="flex-1 text-sm">{task.title}</span>
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-[10px] text-zinc-500">
                      <span>{task.mode === "swarm" ? `${task.size ?? "auto"} agents` : task.assignee}</span>
                      {task.agent_ids.length > 0 && <span>· {task.agent_ids.length} live</span>}
                    </div>
                    {task.status === "running" && (
                      <div className="mt-2 h-1 w-full rounded bg-zinc-800">
                        <div
                          className="h-1 rounded bg-emerald-500 transition-all"
                          style={{ width: `${task.progress}%` }}
                        />
                      </div>
                    )}
                  </div>
                ))}
            </div>
          </div>
        ))}
      </section>

      {/* Detail drawer */}
      {open && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/60"
          onClick={() => setOpen(null)}
        >
          <div
            className="h-full w-full max-w-xl overflow-y-auto border-l border-zinc-800 bg-zinc-950 p-4"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 className="text-lg font-semibold">{open.title}</h2>
            <p className="mt-1 text-xs text-zinc-500">
              {open.status} · {open.progress}% · {open.mode} · {open.model ?? "default model"}
            </p>
            {open.description && (
              <p className="mt-3 whitespace-pre-wrap text-sm text-zinc-300">{open.description}</p>
            )}
            {open.acceptance && (
              <p className="mt-3 rounded-lg border border-zinc-800 p-2 text-sm text-amber-200">
                Acceptance: {open.acceptance}
              </p>
            )}
            {open.agent_ids.length > 0 && (
              <div className="mt-3">
                <h3 className="text-xs uppercase text-zinc-500">Working agents</h3>
                <div className="mt-1 flex flex-wrap gap-1">
                  {open.agent_ids.map((id) => (
                    <span key={id} className="rounded bg-zinc-800 px-2 py-0.5 text-xs">
                      {id}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <div className="mt-3">
              <h3 className="text-xs uppercase text-zinc-500">Activity</h3>
              <div className="mt-1 space-y-1">
                {open.log.map((entry, index) => (
                  <div key={index} className="text-xs text-zinc-400">
                    <span className="text-zinc-600">
                      {new Date(entry.at * 1000).toLocaleTimeString()} · {entry.author}
                    </span>{" "}
                    {entry.message}
                  </div>
                ))}
              </div>
            </div>
            {open.result && (
              <pre className="mt-3 whitespace-pre-wrap rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-xs text-zinc-200">
                {open.result}
              </pre>
            )}
            <div className="mt-4 flex gap-2">
              <button
                onClick={() => startTask(open.id).then(refresh)}
                className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm hover:bg-emerald-500"
              >
                Start
              </button>
              <button
                onClick={() => cancelTask(open.id).then(refresh)}
                className="rounded-lg bg-amber-700 px-3 py-1.5 text-sm hover:bg-amber-600"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteTask(open.id).then(() => { setOpen(null); refresh() })}
                className="rounded-lg bg-red-800 px-3 py-1.5 text-sm hover:bg-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}
