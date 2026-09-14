"use client"

import { useEffect, useRef } from "react"
import type { A2AMessage } from "@/lib/swarm"

const KIND_STYLE: Record<string, string> = {
  chat: "border-zinc-700 text-zinc-300",
  request: "border-sky-700 text-sky-300",
  response: "border-sky-600 text-sky-200",
  proposal: "border-violet-700 text-violet-300",
  critique: "border-amber-700 text-amber-300",
  vote: "border-emerald-700 text-emerald-300",
  handoff: "border-indigo-700 text-indigo-300",
  status: "border-zinc-800 text-zinc-500",
  help: "border-red-700 text-red-300",
  announce: "border-white/40 text-white",
  result: "border-emerald-600 text-emerald-200",
}

/** The "what are they saying to each other" view. */
export function ConversationFeed({
  messages,
  filterAgent,
  filterKind,
}: {
  messages: A2AMessage[]
  filterAgent?: string | null
  filterKind?: string | null
}) {
  const endRef = useRef<HTMLDivElement>(null)
  const visible = messages.filter(
    (m) =>
      (!filterAgent || m.sender === filterAgent || m.recipient === filterAgent) &&
      (!filterKind || m.kind === filterKind),
  )

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [visible.length])

  return (
    <div className="h-full space-y-2 overflow-y-auto pr-1">
      {visible.map((message) => (
        <div
          key={message.id}
          className={`rounded-lg border-l-2 bg-zinc-900/50 px-3 py-2 ${
            KIND_STYLE[message.kind] ?? "border-zinc-700"
          }`}
        >
          <div className="flex items-center gap-2 text-xs">
            <span className="font-semibold">{message.sender}</span>
            <span className="text-zinc-600">→</span>
            <span className="text-zinc-400">
              {message.recipient === "*" ? message.topic : message.recipient}
            </span>
            <span className="ml-auto rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] uppercase">
              {message.kind}
            </span>
            <span className="text-[10px] text-zinc-600">
              {new Date(message.timestamp * 1000).toLocaleTimeString()}
            </span>
          </div>
          <p className="mt-1 whitespace-pre-wrap text-sm text-zinc-200">{message.content}</p>
        </div>
      ))}
      {visible.length === 0 && (
        <p className="text-sm text-zinc-500">No agent conversation yet.</p>
      )}
      <div ref={endRef} />
    </div>
  )
}
