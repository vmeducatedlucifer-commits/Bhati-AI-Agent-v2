"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { API_BASE, health, type HealthInfo } from "@/lib/client";
import { cx } from "@/lib/format";
import CommandPalette from "@/components/shell/CommandPalette";

export const NAV = [
  { href: "/", label: "Cockpit", icon: "◉", hint: "Chat with the main agent" },
  { href: "/swarm", label: "Swarm", icon: "✲", hint: "Agents, graph, blackboard" },
  { href: "/workspace", label: "Workspace", icon: "▤", hint: "Agent files & downloads" },
  { href: "/tasks", label: "Tasks", icon: "✓", hint: "Task panel" },
  { href: "/models", label: "Models", icon: "◈", hint: "Providers & custom models" },
];

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [status, setStatus] = useState<"online" | "offline" | "checking">("checking");
  const [meta, setMeta] = useState<HealthInfo | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    const ping = async () => {
      try {
        const data = await health();
        if (!alive) return;
        setMeta(data);
        setStatus("online");
      } catch {
        if (alive) setStatus("offline");
      }
    };
    ping();
    const timer = setInterval(ping, 20000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
      if (event.key === "Escape") setPaletteOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const providers = (meta?.providers as string[] | undefined) || [];

  return (
    <div className="flex h-screen w-full overflow-hidden">
      {/* nav rail */}
      <aside className="z-20 flex w-[68px] shrink-0 flex-col items-center gap-2 border-r border-white/5 bg-black/40 py-4 backdrop-blur-xl">
        <Link href="/" className="group mb-3 flex flex-col items-center gap-1">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-[rgb(var(--brand))] to-[rgb(var(--brand-2))] text-base font-black text-black shadow-lg">
            B
          </span>
          <span className="text-[9px] font-semibold uppercase tracking-widest text-[rgb(var(--muted))]">
            bhati
          </span>
        </Link>

        {NAV.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              data-active={active}
              title={`${item.label} — ${item.hint}`}
              className="rail-link group"
            >
              <span className="text-lg leading-none">{item.icon}</span>
              <span className="pointer-events-none absolute left-14 z-40 hidden whitespace-nowrap rounded-lg border bg-black/90 px-2.5 py-1.5 text-xs shadow-xl group-hover:block">
                {item.label}
              </span>
            </Link>
          );
        })}

        <div className="mt-auto flex flex-col items-center gap-2">
          <button
            onClick={() => setPaletteOpen(true)}
            title="Command palette (⌘K)"
            className="rail-link"
          >
            <span className="text-base">⌘</span>
          </button>
          <span
            title={status === "online" ? `Backend online · ${API_BASE}` : `Backend unreachable · ${API_BASE}`}
            className={cx(
              "h-2.5 w-2.5 rounded-full",
              status === "online"
                ? "bg-[rgb(var(--ok))] animate-ring"
                : status === "offline"
                  ? "bg-[rgb(var(--err))]"
                  : "bg-[rgb(var(--warn))]",
            )}
          />
        </div>
      </aside>

      {/* main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="z-10 flex h-14 shrink-0 items-center gap-3 border-b border-white/5 bg-black/30 px-5 backdrop-blur-xl">
          <h1 className="text-sm font-semibold tracking-tight">
            <span className="text-gradient">Bhati AI Agent</span>
            <span className="ml-2 rounded-md border px-1.5 py-0.5 text-[10px] font-medium text-[rgb(var(--muted))]">
              v{String(meta?.version || "2.2")}
            </span>
          </h1>

          <nav className="ml-4 hidden items-center gap-1 md:flex">
            {NAV.map((item) => {
              const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cx(
                    "rounded-lg px-3 py-1.5 text-xs font-medium transition",
                    active
                      ? "bg-white/10 text-white"
                      : "text-[rgb(var(--muted))] hover:bg-white/5 hover:text-white",
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => setPaletteOpen(true)}
              className="hidden items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs text-[rgb(var(--muted))] hover:text-white sm:flex"
            >
              Search
              <kbd className="rounded border px-1 text-[10px]">⌘K</kbd>
            </button>
            <span className="chip border text-[rgb(var(--muted))]">
              {providers.length ? `${providers.length} providers` : "builtin model"}
            </span>
            <span
              className={cx(
                "chip border",
                status === "online"
                  ? "text-[rgb(var(--ok))]"
                  : status === "offline"
                    ? "text-[rgb(var(--err))]"
                    : "text-[rgb(var(--warn))]",
              )}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-current" />
              {status}
            </span>
          </div>
        </header>

        <main className="grid-bg min-h-0 flex-1 overflow-auto scroll-thin">{children}</main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
