"use client"

import { useEffect, useState } from "react"
import { getJSON } from "@/lib/api"
import { useStore } from "@/lib/store"

type Node = { name: string; path: string; type: "dir" | "file"; size: number }

export default function FileBrowser() {
  const sessionId = useStore((state) => state.sessionId)
  const [path, setPath] = useState(".")
  const [nodes, setNodes] = useState<Node[]>([])
  const [preview, setPreview] = useState<{ path: string; content: string } | null>(null)

  useEffect(() => {
    if (!sessionId) return
    getJSON<Node[]>(`/api/files/tree?session_id=${sessionId}&path=${encodeURIComponent(path)}`)
      .then(setNodes)
      .catch(() => setNodes([]))
  }, [sessionId, path])

  return (
    <div className="grid gap-3 lg:grid-cols-[260px_1fr]">
      <div className="panel p-3 text-sm">
        <div className="mb-2 flex items-center justify-between">
          <span className="chip">workspace</span>
          {path !== "." && (
            <button
              className="btn py-0.5"
              onClick={() => setPath(path.split("/").slice(0, -1).join("/") || ".")}
            >
              up
            </button>
          )}
        </div>
        {nodes.length === 0 && <p className="text-xs text-slate-500">empty</p>}
        {nodes.map((node) => (
          <button
            key={node.path}
            className="block w-full truncate py-1 text-left hover:text-accent"
            onClick={() => {
              if (node.type === "dir") {
                setPath(node.path)
              } else {
                void getJSON<{ path: string; content: string }>(
                  `/api/files/read?session_id=${sessionId}&path=${encodeURIComponent(node.path)}`,
                ).then(setPreview)
              }
            }}
          >
            {node.type === "dir" ? "[dir]" : "[file]"} {node.name}
          </button>
        ))}
      </div>
      <div className="panel min-h-[320px] p-3">
        {preview ? (
          <>
            <p className="chip mb-2">{preview.path}</p>
            <pre className="overflow-auto text-xs leading-relaxed text-slate-300">{preview.content}</pre>
          </>
        ) : (
          <p className="text-sm text-slate-500">Select a file to preview.</p>
        )}
      </div>
    </div>
  )
}
