"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { NAV } from "@/components/shell/AppShell";
import { cx } from "@/lib/format";

type Command = { label: string; hint: string; run: () => void };

export default function CommandPalette({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);

  const commands: Command[] = useMemo(
    () => [
      ...NAV.map((item) => ({
        label: `Go to ${item.label}`,
        hint: item.hint,
        run: () => router.push(item.href),
      })),
      {
        label: "Launch a swarm",
        hint: "Open the swarm console",
        run: () => router.push("/swarm"),
      },
      {
        label: "Download agent files",
        hint: "Workspace explorer → export zip",
        run: () => router.push("/workspace"),
      },
      {
        label: "Reload API docs",
        hint: "Open FastAPI /docs",
        run: () => window.open(`${process.env.NEXT_PUBLIC_API_URL || ""}/docs`, "_blank"),
      },
    ],
    [router],
  );

  const filtered = commands.filter((command) =>
    `${command.label} ${command.hint}`.toLowerCase().includes(query.toLowerCase()),
  );

  useEffect(() => {
    if (open) {
      setQuery("");
      setCursor(0);
    }
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 p-4 pt-[14vh] backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="glass float-in w-full max-w-lg overflow-hidden p-0"
        onClick={(event) => event.stopPropagation()}
      >
        <input
          autoFocus
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setCursor(0);
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") setCursor((c) => Math.min(c + 1, filtered.length - 1));
            if (event.key === "ArrowUp") setCursor((c) => Math.max(c - 1, 0));
            if (event.key === "Enter" && filtered[cursor]) {
              filtered[cursor].run();
              onClose();
            }
          }}
          placeholder="Type a command or page…"
          className="w-full border-b bg-transparent px-4 py-3.5 text-sm outline-none placeholder:text-[rgb(var(--muted))]"
        />
        <ul className="max-h-72 overflow-auto scroll-thin p-2">
          {filtered.map((command, index) => (
            <li key={command.label}>
              <button
                onMouseEnter={() => setCursor(index)}
                onClick={() => {
                  command.run();
                  onClose();
                }}
                className={cx(
                  "flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm",
                  index === cursor ? "bg-white/10" : "hover:bg-white/5",
                )}
              >
                <span>{command.label}</span>
                <span className="text-xs text-[rgb(var(--muted))]">{command.hint}</span>
              </button>
            </li>
          ))}
          {!filtered.length && (
            <li className="px-3 py-6 text-center text-sm text-[rgb(var(--muted))]">
              No matching command
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}
