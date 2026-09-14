"use client"

import { useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { streamChat } from "@/lib/api"
import { useStore } from "@/lib/store"
import VoiceButton from "@/components/VoiceButton"

export default function ChatPanel() {
  const [input, setInput] = useState("")
  const bottom = useRef<HTMLDivElement>(null)
  const {
    messages,
    addMessage,
    appendToLast,
    sessionId,
    setSession,
    mode,
    profile,
    busy,
    setBusy,
    upsertTask,
    setTasks,
    pushTool,
    setAgent,
  } = useStore()

  async function send(text: string) {
    if (!text.trim() || busy) return
    addMessage({ id: crypto.randomUUID(), role: "user", content: text })
    setInput("")
    setBusy(true)
    addMessage({ id: crypto.randomUUID(), role: "assistant", content: "" })
    try {
      for await (const event of streamChat({ message: text, session_id: sessionId, mode, profile })) {
        const data = event.data ?? (event as any)
        switch (event.type) {
          case "session":
            if (data.session_id) setSession(data.session_id)
            break
          case "message_delta":
            appendToLast(data.text ?? "")
            break
          case "plan_created":
            setTasks(data.plan?.tasks ?? [])
            break
          case "task_updated":
            if (data.task) upsertTask(data.task)
            break
          case "tool_call":
            pushTool({ name: data.name, agent: event.agent_id, at: Date.now() })
            break
          case "tool_result":
            pushTool({
              name: data.name,
              ok: data.ok,
              preview: data.preview,
              agent: event.agent_id,
              at: Date.now(),
            })
            break
          case "agent_start":
            setAgent(event.agent_id ?? "main", "running")
            break
          case "agent_end":
            setAgent(event.agent_id ?? "main", "done")
            break
          case "final":
            if (data.content) appendToLast(data.content)
            break
          case "error":
            appendToLast(`\n\n**Error:** ${data.error}`)
            break
        }
        bottom.current?.scrollIntoView({ behavior: "smooth" })
      }
    } catch (error) {
      appendToLast(`\n\n**Connection error:** ${String(error)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 space-y-4 overflow-auto p-4">
        {messages.length === 0 && (
          <div className="panel p-4 text-sm text-slate-400">
            <p className="mb-2 text-accent">Bhati AI Agent v2</p>
            <p>Ask anything, or switch to Auto mode to let the planner spawn parallel specialists.</p>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-500">
              <li>Clone my repo, fix failing tests and open a PR</li>
              <li>Research competitors and write a report</li>
              <li>Open the browser and complete this booking</li>
            </ul>
          </div>
        )}
        {messages.map((message) => (
          <div
            key={message.id}
            className={`panel p-3 text-sm ${message.role === "user" ? "border-accent2/40" : ""}`}
          >
            <p className="chip mb-2">{message.role}</p>
            <div className="prose prose-invert max-w-none prose-pre:bg-ink prose-pre:text-xs">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || "..."}</ReactMarkdown>
            </div>
          </div>
        ))}
        <div ref={bottom} />
      </div>

      <div className="border-t border-edge p-3">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault()
                void send(input)
              }
            }}
            rows={2}
            placeholder={mode === "autonomous" ? "Describe the goal..." : "Message Bhati..."}
            className="min-h-[54px] flex-1 resize-none rounded-lg border border-edge bg-ink p-2 text-sm outline-none focus:border-accent"
          />
          <VoiceButton onTranscript={(text) => void send(text)} />
          <button className="btn-primary h-[54px]" disabled={busy} onClick={() => void send(input)}>
            {busy ? "Working" : "Send"}
          </button>
        </div>
      </div>
    </div>
  )
}
