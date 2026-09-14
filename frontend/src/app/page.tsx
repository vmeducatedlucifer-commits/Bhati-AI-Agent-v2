"use client"

import { useEffect, useState } from "react"
import ChatPanel from "@/components/ChatPanel"
import PlanGraph from "@/components/PlanGraph"
import TerminalGrid from "@/components/TerminalGrid"
import FileBrowser from "@/components/FileBrowser"
import ActivityFeed from "@/components/ActivityFeed"
import Sidebar from "@/components/Sidebar"
import { useStore } from "@/lib/store"

type Tab = "plan" | "terminals" | "files" | "activity"

export default function Home() {
  const [tab, setTab] = useState<Tab>("plan")
  const { sessionId, setSession } = useStore()

  useEffect(() => {
    if (!sessionId) setSession(crypto.randomUUID().replace(/-/g, "").slice(0, 16))
  }, [sessionId, setSession])

  const tabs: Tab[] = ["plan", "terminals", "files", "activity"]

  return (
    <main className="flex h-screen">
      <Sidebar />
      <section className="flex min-w-0 flex-1">
        <div className="flex w-[46%] min-w-[380px] flex-col border-r border-edge">
          <ChatPanel />
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex gap-2 border-b border-edge px-4 py-2">
            {tabs.map((name) => (
              <button
                key={name}
                onClick={() => setTab(name)}
                className={`btn capitalize ${tab === name ? "border-accent text-accent" : ""}`}
              >
                {name}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-4">
            {tab === "plan" && <PlanGraph />}
            {tab === "terminals" && <TerminalGrid />}
            {tab === "files" && <FileBrowser />}
            {tab === "activity" && <ActivityFeed />}
          </div>
        </div>
      </section>
    </main>
  )
}
