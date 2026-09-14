"use client"

import { create } from "zustand"

export type Msg = { id: string; role: "user" | "assistant" | "system"; content: string }
export type Task = {
  id: string
  title: string
  agent: string
  status: string
  depends_on: string[]
  result?: string
}
export type ToolEvent = { name: string; ok?: boolean; agent?: string; preview?: string; at: number }

type State = {
  sessionId: string
  mode: "chat" | "autonomous"
  profile: string
  busy: boolean
  messages: Msg[]
  tasks: Task[]
  toolEvents: ToolEvent[]
  agents: Record<string, string>
  setSession: (id: string) => void
  setMode: (mode: "chat" | "autonomous") => void
  setProfile: (profile: string) => void
  setBusy: (busy: boolean) => void
  addMessage: (msg: Msg) => void
  appendToLast: (text: string) => void
  setTasks: (tasks: Task[]) => void
  upsertTask: (task: Task) => void
  pushTool: (event: ToolEvent) => void
  setAgent: (id: string, status: string) => void
  reset: () => void
}

export const useStore = create<State>((set) => ({
  sessionId: "",
  mode: "chat",
  profile: "general",
  busy: false,
  messages: [],
  tasks: [],
  toolEvents: [],
  agents: {},
  setSession: (sessionId) => set({ sessionId }),
  setMode: (mode) => set({ mode }),
  setProfile: (profile) => set({ profile }),
  setBusy: (busy) => set({ busy }),
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),
  appendToLast: (text) =>
    set((state) => {
      const messages = [...state.messages]
      const last = messages[messages.length - 1]
      if (last && last.role === "assistant") {
        messages[messages.length - 1] = { ...last, content: last.content + text }
      } else {
        messages.push({ id: crypto.randomUUID(), role: "assistant", content: text })
      }
      return { messages }
    }),
  setTasks: (tasks) => set({ tasks }),
  upsertTask: (task) =>
    set((state) => ({
      tasks: state.tasks.some((item) => item.id === task.id)
        ? state.tasks.map((item) => (item.id === task.id ? task : item))
        : [...state.tasks, task],
    })),
  pushTool: (event) => set((state) => ({ toolEvents: [event, ...state.toolEvents].slice(0, 200) })),
  setAgent: (id, status) => set((state) => ({ agents: { ...state.agents, [id]: status } })),
  reset: () => set({ messages: [], tasks: [], toolEvents: [], agents: {} }),
}))
