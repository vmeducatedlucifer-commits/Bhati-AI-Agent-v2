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
import { workspace } from "@/lib/client"
import { Button, Empty, Panel } from "@/components/ui/Primitives"
import { cx } from "@/lib/format"
import { useStore } from "@/lib/store"

const COLUMNS = [
  { key: "queued", label: "Queued", tone: "bg-white/25" },
  { key: "running", label: "Running", tone: "bg-[rgb(var(--brand-2))]" },
  { key: "review", label: "Review", tone: "bg-[rgb(var(--warn))]" },
  { key: "done", label: "Done", tone: "bg-[rgb(var(--ok))]" },
  { key: "failed", label: "Failed / Cancelled", tone: "bg-[rgb(var(--err))]" },
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
    <div className="mx-auto flex h-full max-w-[1700px] flex-col gap-4 p-4 lg:p-6">
      <Panel
        title="Task panel"
        subtitle="Assign work here — the swarm has to finish it and leave the files in the workspace"
        bodyClassName="grid gap-3 p-4 md:grid-cols-[2fr_1fr]"
        actions={<Button onClick={() => startAll(sessionId).then(refresh)}>Start all queued</Button>}
      >
        <div className="space-y-2">
          <input
            value={form.title}
            onChange={(event) => setForm({ ...form, title: event.target.value })}
            placeholder="Task title — what must be done"
            className="input"
          />
          <textarea
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
            placeholder="Details, constraints, links, repo paths…"
            rows={3}
            className="input resize-none"
          />
          <input
            value={form.acceptance}
            onChange={(event) => setForm({ ...form, acceptance: event.target.value })}
            placeholder="Acceptance criteria — how we know it's truly done"
            className="input"
          />
        </div>
        <div className="space-y-2 text-sm">
          <div className="flex gap-2">
            <select
              value={form.mode}
              onChange={(event) => setForm({ ...form, mode: event.target.value })}
              className="input flex-1"
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
              className="input w-24"
              title="Swarm size"
            />
          </div>
          <select
            value={form.assignee}
            onChange={(event) => setForm({ ...form, assignee: event.target.value })}
            className="input"
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
              className="input w-20"
              title="Priority (1 = highest)"
            />
            <input
              value={form.model}
              onChange={(event) => setForm({ ...form, model: event.target.value })}
              placeholder="model override"
              className="input flex-1"
            />
          </div>
          <Button variant="primary" className="w-full" onClick={submit}>
            Assign to swarm
          </Button>
        </div>
      </Panel>

      <section className="grid min-h-0 flex-1 grid-cols-1 gap-4 md:grid-cols-3 xl:grid-cols-5">
        {COLUMNS.map((col) => {
          const items = tasks.filter((task) => column(task) === col.key)
          return (
            <div key={col.key} className="glass flex min-h-0 flex-col p-2">
              <h2 className="flex items-center gap-2 px-2 py-2 text-[11px] font-semibold uppercase tracking-wider text-[rgb(var(--muted))]">
                <span className={cx("h-1.5 w-1.5 rounded-full", col.tone)} />
                {col.label}
                <span className="ml-auto rounded-md border px-1.5 text-[10px]">{items.length}</span>
              </h2>
              <div className="min-h-0 flex-1 space-y-2 overflow-y-auto scroll-thin p-1">
                {!items.length && <Empty icon="—" text="Empty" />}
                {items.map((task) => (
                  <button
                    key={task.id}
                    onClick={() => setOpen(task)}
                    className="float-in w-full rounded-xl border bg-black/30 p-2.5 text-left transition hover:border-[rgb(var(--brand))]/50"
                  >
                    <div className="flex items-start gap-2">
                      <span className="chip border text-[10px] text-[rgb(var(--muted))]">P{task.priority}</span>
                      <span className="flex-1 text-sm leading-snug">{task.title}</span>
                    </div>
                    <div className="mt-1.5 flex items-center gap-2 text-[10px] text-[rgb(var(--muted))]">
                      <span>{task.mode === "swarm" ? `${task.size ?? "auto"} agents` : task.assignee}</span>
                      {task.agent_ids.length > 0 && <span>· {task.agent_ids.length} live</span>}
                    </div>
                    {task.status === "running" && (
                      <div className="mt-2 h-1 w-full overflow-hidden rounded bg-white/10">
                        <div
                          className="h-1 rounded bg-gradient-to-r from-[rgb(var(--brand))] to-[rgb(var(--brand-2))] transition-all"
                          style={{ width: `${task.progress}%` }}
                        />
                      </div>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )
        })}
      </section>

      {open && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/70 backdrop-blur-sm" onClick={() => setOpen(null)}>
          <div
            className="float-in h-full w-full max-w-xl overflow-y-auto scroll-thin border-l bg-[rgb(var(--bg-soft))] p-5"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 className="text-lg font-semibold">{open.title}</h2>
            <p className="mt-1 text-xs text-[rgb(var(--muted))]">
              {open.status} · {open.progress}% · {open.mode} · {open.model ?? "default model"}
            </p>

            {open.description && (
              <p className="mt-4 whitespace-pre-wrap text-sm text-[rgb(var(--text))]/85">{open.description}</p>
            )}
            {open.acceptance && (
              <p className="mt-4 rounded-xl border p-3 text-sm text-[rgb(var(--warn))]">
                Acceptance: {open.acceptance}
              </p>
            )}

            {open.agent_ids.length > 0 && (
              <div className="mt-4">
                <h3 className="text-[11px] uppercase tracking-wider text-[rgb(var(--muted))]">Working agents</h3>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {open.agent_ids.map((id) => (
                    <a
                      key={id}
                      href={workspace.archiveUrl(sessionId, `agents/${id}`)}
                      download
                      title="Download this agent's files"
                      className="chip border hover:border-[rgb(var(--brand))]/60"
                    >
                      🤖 {id} ↓
                    </a>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-4">
              <h3 className="text-[11px] uppercase tracking-wider text-[rgb(var(--muted))]">Activity</h3>
              <div className="mt-2 space-y-1">
                {open.log.map((entry, index) => (
                  <div key={index} className="text-xs text-[rgb(var(--text))]/75">
                    <span className="text-[rgb(var(--muted))]">
                      {new Date(entry.at * 1000).toLocaleTimeString()} · {entry.author}
                    </span>{" "}
                    {entry.message}
                  </div>
                ))}
              </div>
            </div>

            {open.result && (
              <pre className="mt-4 whitespace-pre-wrap rounded-xl border bg-black/40 p-3 text-xs">{open.result}</pre>
            )}

            <div className="mt-5 flex flex-wrap gap-2">
              <Button variant="primary" onClick={() => startTask(open.id).then(refresh)}>
                Start
              </Button>
              <Button onClick={() => cancelTask(open.id).then(refresh)}>Cancel</Button>
              <a href={workspace.archiveUrl(sessionId)} download className="btn btn-ghost">
                Download workspace
              </a>
              <Button
                variant="danger"
                onClick={() =>
                  deleteTask(open.id).then(() => {
                    setOpen(null)
                    refresh()
                  })
                }
              >
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
