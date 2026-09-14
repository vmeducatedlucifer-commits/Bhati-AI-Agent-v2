"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { API, getJSON, postJSON } from "@/lib/api"
import { useStore } from "@/lib/store"

type TerminalInfo = { id: string; agent_id: string; cwd: string; alive?: boolean }

function TerminalView({ info }: { info: TerminalInfo }) {
  const host = useRef<HTMLDivElement>(null)
  const socket = useRef<WebSocket | null>(null)

  useEffect(() => {
    let term: any
    let disposed = false
    void (async () => {
      const { Terminal } = await import("@xterm/xterm")
      const { FitAddon } = await import("@xterm/addon-fit")
      // @ts-expect-error css import
      await import("@xterm/xterm/css/xterm.css")
      if (disposed || !host.current) return
      term = new Terminal({
        fontSize: 12,
        theme: { background: "#0e1118", foreground: "#cbd5e1" },
        cursorBlink: true,
      })
      const fit = new FitAddon()
      term.loadAddon(fit)
      term.open(host.current)
      fit.fit()

      const ws = new WebSocket(`${API.replace(/^http/, "ws")}/api/terminals/ws/${info.id}`)
      socket.current = ws
      ws.onmessage = (event) => {
        const payload = JSON.parse(event.data)
        if (payload.type === "history" || payload.type === "output") term.write(payload.data)
        if (payload.type === "error") term.writeln(`\r\n[${payload.message}]`)
      }
      term.onData((data: string) => {
        if (ws.readyState === 1) ws.send(JSON.stringify({ type: "input", data }))
      })
    })()
    return () => {
      disposed = true
      socket.current?.close()
      term?.dispose?.()
    }
  }, [info.id])

  return (
    <div className="panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-edge px-3 py-1.5 text-xs text-slate-400">
        <span className="text-accent">{info.agent_id}</span>
        <span className="truncate">{info.cwd}</span>
      </div>
      <div ref={host} className="h-64" />
    </div>
  )
}

export default function TerminalGrid() {
  const sessionId = useStore((state) => state.sessionId)
  const [terminals, setTerminals] = useState<TerminalInfo[]>([])

  const refresh = useCallback(async () => {
    if (!sessionId) return
    try {
      setTerminals(await getJSON<TerminalInfo[]>(`/api/terminals?session_id=${sessionId}`))
    } catch {
      setTerminals([])
    }
  }, [sessionId])

  useEffect(() => {
    void refresh()
    const timer = setInterval(() => void refresh(), 5000)
    return () => clearInterval(timer)
  }, [refresh])

  async function spawn() {
    await postJSON("/api/terminals", {
      session_id: sessionId,
      agent_id: `term-${terminals.length + 1}`,
    })
    await refresh()
  }

  return (
    <div className="space-y-3">
      <button className="btn" onClick={() => void spawn()}>
        + New terminal
      </button>
      <div className="grid gap-3 xl:grid-cols-2">
        {terminals.map((terminal) => (
          <TerminalView key={terminal.id} info={terminal} />
        ))}
      </div>
      {terminals.length === 0 && (
        <p className="text-sm text-slate-500">
          No terminals yet. Agents spawn their own, or create one manually.
        </p>
      )}
    </div>
  )
}
