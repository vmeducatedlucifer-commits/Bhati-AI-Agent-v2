"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  listModels,
  streamChat,
  subscribeEvents,
  workspace,
  type ModelEntry,
  type WorkspaceStats,
} from "@/lib/client";
import { Button, Empty, Panel, Spinner, Stat } from "@/components/ui/Primitives";
import { cx, formatBytes } from "@/lib/format";

type ChatMessage = { role: "user" | "assistant"; content: string; ts: number };
type Activity = { id: string; type: string; text: string; agent?: string; ts: number };

const SUGGESTIONS = [
  "Build a FastAPI + React todo app in my workspace",
  "Research the top 5 AI agent frameworks and write a report",
  "Analyse this repo and list the 10 worst code smells",
  "Launch a 12-agent swarm to plan a SaaS launch",
];

export default function Cockpit() {
  const [sessionId] = useState(() => {
    if (typeof window === "undefined") return "web";
    const existing = window.localStorage.getItem("bhati.session");
    if (existing) return existing;
    const fresh = `web-${Math.random().toString(36).slice(2, 10)}`;
    window.localStorage.setItem("bhati.session", fresh);
    return fresh;
  });

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [model, setModel] = useState("builtin/gemini-2.0-flash");
  const [stats, setStats] = useState<WorkspaceStats | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listModels()
      .then((data) => setModels(data.models || []))
      .catch(() => setModels([]));
  }, []);

  useEffect(() => {
    const load = () =>
      workspace
        .overview(sessionId)
        .then(setStats)
        .catch(() => undefined);
    load();
    const timer = setInterval(load, 8000);
    return () => clearInterval(timer);
  }, [sessionId]);

  useEffect(() => {
    const stop = subscribeEvents(sessionId, (event) => {
      const data = (event.data || {}) as Record<string, unknown>;
      const text =
        (data.name as string) ||
        (data.text as string) ||
        (data.error as string) ||
        (data.goal as string) ||
        "";
      if (event.type === "message_delta") return;
      setActivity((items) =>
        [
          {
            id: `${Date.now()}-${Math.random()}`,
            type: event.type,
            text: String(text).slice(0, 200),
            agent: event.agent_id,
            ts: Date.now(),
          },
          ...items,
        ].slice(0, 80),
      );
    });
    return stop;
  }, [sessionId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const modelOptions = useMemo(() => {
    const ids = models.map((entry) => entry.id).filter(Boolean);
    const builtins = ["builtin/gemini-2.0-flash", "builtin/gemini-1.5-pro"];
    return Array.from(new Set([...builtins, ...ids]));
  }, [models]);

  const send = async (text?: string) => {
    const prompt = (text ?? input).trim();
    if (!prompt || busy) return;
    setInput("");
    setMessages((items) => [...items, { role: "user", content: prompt, ts: Date.now() }]);
    setMessages((items) => [...items, { role: "assistant", content: "", ts: Date.now() }]);
    setBusy(true);
    try {
      await streamChat({ session_id: sessionId, message: prompt, model }, (token) => {
        setMessages((items) => {
          const copy = [...items];
          const last = copy[copy.length - 1];
          if (last?.role === "assistant") copy[copy.length - 1] = { ...last, content: last.content + token };
          return copy;
        });
      });
    } catch (error) {
      setMessages((items) => {
        const copy = [...items];
        copy[copy.length - 1] = {
          role: "assistant",
          content: `⚠️ ${String(error)}`,
          ts: Date.now(),
        };
        return copy;
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex h-full max-w-[1500px] flex-col gap-4 p-4 lg:p-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Session" value={sessionId} hint="Isolated workspace per session" />
        <Stat label="Workspace files" value={stats?.files ?? 0} hint={formatBytes(stats?.bytes || 0)} tone="ok" />
        <Stat label="Agent folders" value={stats?.agents?.length ?? 0} hint="agents/ shared/ downloads/" tone="warn" />
        <Stat label="Model" value={model.split("/").pop()} hint={model.startsWith("builtin") ? "keyless built-in" : "external provider"} />
      </div>

      <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Panel
          title="Main agent"
          subtitle="Full tool access: shell, files, browser, python, git, device, swarm"
          bodyClassName="flex flex-col gap-4"
          actions={
            <select
              value={model}
              onChange={(event) => setModel(event.target.value)}
              className="rounded-lg border bg-black/40 px-2 py-1.5 text-xs outline-none"
            >
              {modelOptions.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          }
        >
          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto scroll-thin pr-1">
            {!messages.length && (
              <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
                <h2 className="text-2xl font-semibold">
                  <span className="text-gradient">What should the swarm build today?</span>
                </h2>
                <div className="flex max-w-xl flex-wrap justify-center gap-2">
                  {SUGGESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      onClick={() => send(suggestion)}
                      className="rounded-xl border px-3 py-2 text-xs text-[rgb(var(--muted))] transition hover:border-[rgb(var(--brand))]/50 hover:text-white"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((message, index) => (
              <div
                key={index}
                className={cx(
                  "float-in max-w-[86%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-relaxed",
                  message.role === "user"
                    ? "ml-auto bg-gradient-to-br from-[rgb(var(--brand))]/30 to-[rgb(var(--brand-2))]/15 border"
                    : "mr-auto border bg-black/35",
                )}
              >
                {message.content || (busy && index === messages.length - 1 ? <Spinner label="thinking…" /> : "")}
              </div>
            ))}
            <div ref={endRef} />
          </div>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              send();
            }}
            className="flex items-end gap-2"
          >
            <textarea
              value={input}
              rows={2}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  send();
                }
              }}
              placeholder="Give the agent a goal…  (Enter to send, Shift+Enter for a new line)"
              className="input min-h-[52px] resize-none"
            />
            <Button type="submit" variant="primary" disabled={busy || !input.trim()}>
              {busy ? "Running…" : "Send"}
            </Button>
          </form>
        </Panel>

        <div className="flex min-h-0 flex-col gap-4">
          <Panel
            title="Live activity"
            subtitle="Tool calls, plans and agent events"
            className="min-h-0 flex-1"
            bodyClassName="space-y-2 p-3"
          >
            {!activity.length && <Empty icon="📡" text="No events yet. Send a goal to see the agent work in real time." />}
            {activity.map((item) => (
              <div key={item.id} className="float-in rounded-xl border bg-black/25 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-[rgb(var(--brand-2))]">
                    {item.type}
                  </span>
                  <span className="text-[10px] text-[rgb(var(--muted))]">
                    {new Date(item.ts).toLocaleTimeString()}
                  </span>
                </div>
                {item.text && <p className="mt-1 break-words text-xs text-[rgb(var(--muted))]">{item.text}</p>}
                {item.agent && <p className="mt-0.5 text-[10px] text-[rgb(var(--muted))]">@{item.agent}</p>}
              </div>
            ))}
          </Panel>

          <Panel title="Artifacts" subtitle="Files created by agents in this session" bodyClassName="space-y-2 p-3">
            {!stats?.agents?.length && <Empty icon="📁" text="Agent folders appear here as soon as work starts." />}
            {(stats?.agents || []).slice(0, 6).map((agent) => (
              <div key={agent.agent_id} className="flex items-center justify-between rounded-xl border bg-black/25 px-3 py-2 text-xs">
                <span className="truncate">{agent.agent_id}</span>
                <span className="text-[rgb(var(--muted))]">
                  {agent.files} files · {formatBytes(agent.bytes)}
                </span>
              </div>
            ))}
            <div className="flex gap-2 pt-1">
              <Link href="/workspace" className="btn btn-ghost flex-1 text-xs">
                Open workspace
              </Link>
              <a
                href={workspace.archiveUrl(sessionId)}
                className="btn btn-primary flex-1 text-xs"
                download
              >
                Download all (.zip)
              </a>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
