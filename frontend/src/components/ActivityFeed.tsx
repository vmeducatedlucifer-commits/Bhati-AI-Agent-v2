"use client"

import { useStore } from "@/lib/store"

export default function ActivityFeed() {
  const toolEvents = useStore((state) => state.toolEvents)

  if (toolEvents.length === 0) {
    return <p className="text-sm text-slate-500">Tool calls from every agent will stream here.</p>
  }

  return (
    <div className="space-y-2">
      {toolEvents.map((event, index) => (
        <div key={`${event.at}-${index}`} className="panel p-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-accent2">{event.name}</span>
            <span className="text-slate-500">
              {event.agent ?? "main"} - {event.ok === undefined ? "called" : event.ok ? "ok" : "failed"}
            </span>
          </div>
          {event.preview && (
            <pre className="mt-1 max-h-32 overflow-auto text-slate-400">{event.preview}</pre>
          )}
        </div>
      ))}
    </div>
  )
}
