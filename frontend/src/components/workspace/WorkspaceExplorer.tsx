"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  workspace,
  type FileNode,
  type FilePreview,
  type WorkspaceSession,
  type WorkspaceStats,
} from "@/lib/client";
import { Button, Empty, Panel, Spinner, Stat } from "@/components/ui/Primitives";
import { cx, fileIcon, formatBytes, timeAgo } from "@/lib/format";

function Tree({
  nodes,
  depth,
  selected,
  onSelect,
}: {
  nodes: FileNode[];
  depth: number;
  selected: string | null;
  onSelect: (node: FileNode) => void;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  return (
    <ul className="space-y-0.5">
      {nodes.map((node) => {
        const isOpen = open[node.path] ?? depth < 1;
        return (
          <li key={node.path}>
            <button
              onClick={() => {
                if (node.type === "dir") setOpen((state) => ({ ...state, [node.path]: !isOpen }));
                else onSelect(node);
              }}
              style={{ paddingLeft: 8 + depth * 14 }}
              className={cx(
                "group flex w-full items-center gap-2 rounded-lg py-1.5 pr-2 text-left text-xs transition",
                selected === node.path ? "bg-white/10 text-white" : "hover:bg-white/5",
              )}
            >
              <span className="w-4 text-center">
                {node.type === "dir" ? (isOpen ? "▾" : "▸") : fileIcon(node.name)}
              </span>
              <span className="truncate">{node.name}</span>
              {node.type === "file" && (
                <span className="ml-auto shrink-0 text-[10px] text-[rgb(var(--muted))]">
                  {formatBytes(node.size)}
                </span>
              )}
            </button>
            {node.type === "dir" && isOpen && node.children?.length ? (
              <Tree nodes={node.children} depth={depth + 1} selected={selected} onSelect={onSelect} />
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

export default function WorkspaceExplorer() {
  const [sessions, setSessions] = useState<WorkspaceSession[]>([]);
  const [sessionId, setSessionId] = useState<string>("");
  const [stats, setStats] = useState<WorkspaceStats | null>(null);
  const [nodes, setNodes] = useState<FileNode[]>([]);
  const [scope, setScope] = useState<string>("");
  const [preview, setPreview] = useState<FilePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const uploadRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    workspace
      .sessions()
      .then((data) => {
        setSessions(data.sessions);
        const stored =
          typeof window !== "undefined" ? window.localStorage.getItem("bhati.session") : null;
        setSessionId((current) => current || stored || data.sessions[0]?.session_id || "");
      })
      .catch(() => setSessions([]));
  }, []);

  const refresh = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const [overview, tree] = await Promise.all([
        workspace.overview(sessionId),
        workspace.tree(sessionId, scope),
      ]);
      setStats(overview);
      setNodes(tree.nodes);
    } catch {
      setNodes([]);
    } finally {
      setLoading(false);
    }
  }, [sessionId, scope]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 10000);
    return () => clearInterval(timer);
  }, [refresh]);

  const openFile = async (node: FileNode) => {
    try {
      setPreview(await workspace.preview(sessionId, node.path));
    } catch {
      setPreview(null);
    }
  };

  return (
    <div className="mx-auto flex h-full max-w-[1600px] flex-col gap-4 p-4 lg:p-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Sessions" value={sessions.length} hint="one workspace per session" />
        <Stat label="Files" value={stats?.files ?? 0} hint={formatBytes(stats?.bytes || 0)} tone="ok" />
        <Stat label="Agent folders" value={stats?.agents?.filter((a) => !a.special).length ?? 0} hint="agents/<id>/" tone="warn" />
        <Stat
          label="Storage"
          value={stats?.ephemeral ? "Ephemeral" : "Persistent"}
          hint={stats?.path || "-"}
          tone={stats?.ephemeral ? "err" : "ok"}
        />
      </div>

      <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
        <div className="flex min-h-0 flex-col gap-4">
          <Panel
            title="Session"
            subtitle="Pick a workspace to browse"
            bodyClassName="space-y-2 p-3"
            actions={<Button onClick={refresh}>{loading ? "…" : "Refresh"}</Button>}
          >
            <select
              value={sessionId}
              onChange={(event) => {
                setSessionId(event.target.value);
                setScope("");
                setPreview(null);
              }}
              className="input"
            >
              {!sessions.length && <option value="">No workspaces yet</option>}
              {sessions.map((session) => (
                <option key={session.session_id} value={session.session_id}>
                  {session.session_id} — {session.files} files
                </option>
              ))}
            </select>

            <div className="space-y-1.5 pt-1">
              <button
                onClick={() => setScope("")}
                className={cx(
                  "flex w-full items-center justify-between rounded-xl border px-3 py-2 text-xs",
                  scope === "" ? "bg-white/10 text-white" : "hover:bg-white/5",
                )}
              >
                <span>Whole session</span>
                <span className="text-[rgb(var(--muted))]">{stats?.files ?? 0}</span>
              </button>
              {(stats?.agents || []).map((agent) => (
                <button
                  key={agent.agent_id}
                  onClick={() => {
                    setScope(agent.path);
                    setPreview(null);
                  }}
                  className={cx(
                    "flex w-full items-center justify-between rounded-xl border px-3 py-2 text-xs",
                    scope === agent.path ? "bg-white/10 text-white" : "hover:bg-white/5",
                  )}
                >
                  <span className="truncate">
                    {agent.special ? "📦" : "🤖"} {agent.agent_id}
                  </span>
                  <span className="shrink-0 text-[rgb(var(--muted))]">
                    {agent.files} · {formatBytes(agent.bytes)}
                  </span>
                </button>
              ))}
            </div>
          </Panel>

          <Panel title="Export" bodyClassName="space-y-2 p-3">
            <a
              href={sessionId ? workspace.archiveUrl(sessionId, scope) : "#"}
              download
              className="btn btn-primary w-full text-xs"
            >
              Download {scope ? scope : "session"} (.zip)
            </a>
            <a
              href={sessionId ? workspace.archiveUrl(sessionId, "downloads") : "#"}
              download
              className="btn btn-ghost w-full text-xs"
            >
              Download final deliverables
            </a>
            <input
              ref={uploadRef}
              type="file"
              className="hidden"
              onChange={async (event) => {
                const file = event.target.files?.[0];
                if (!file || !sessionId) return;
                await workspace.upload(sessionId, file, scope);
                refresh();
              }}
            />
            <Button className="w-full text-xs" onClick={() => uploadRef.current?.click()}>
              Upload file to agents
            </Button>
          </Panel>
        </div>

        <div className="grid min-h-0 gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
          <Panel
            title="Files"
            subtitle={scope || "session root"}
            className="min-h-0"
            bodyClassName="p-2"
          >
            {loading && !nodes.length ? (
              <Spinner label="loading tree…" />
            ) : nodes.length ? (
              <Tree nodes={nodes} depth={0} selected={preview?.path || null} onSelect={openFile} />
            ) : (
              <Empty icon="🗂️" text="No files yet. Agents create files here while they work." />
            )}
          </Panel>

          <Panel
            title={preview ? preview.name : "Preview"}
            subtitle={
              preview
                ? `${formatBytes(preview.size)} · ${preview.mime} · ${timeAgo(preview.modified)}`
                : "Select a file to preview it"
            }
            className="min-h-0"
            bodyClassName="p-0"
            actions={
              preview ? (
                <div className="flex gap-2">
                  <a
                    href={workspace.downloadUrl(sessionId, preview.path)}
                    download
                    className="btn btn-primary text-xs"
                  >
                    Download
                  </a>
                  <Button
                    variant="danger"
                    className="text-xs"
                    onClick={async () => {
                      await workspace.remove(sessionId, preview.path);
                      setPreview(null);
                      refresh();
                    }}
                  >
                    Delete
                  </Button>
                </div>
              ) : null
            }
          >
            {!preview && <Empty icon="👁️" text="Click any file in the tree to read it here." />}
            {preview?.binary && (
              <div className="p-6">
                <Empty icon="📦" text="Binary file — use Download to get it." />
              </div>
            )}
            {preview && !preview.binary && (
              <pre className="h-full overflow-auto scroll-thin p-4 text-xs leading-relaxed text-[rgb(var(--text))]">
                <code>{preview.text}</code>
              </pre>
            )}
            {preview?.truncated && (
              <p className="border-t px-4 py-2 text-xs text-[rgb(var(--warn))]">
                Preview truncated — download the file for the full content.
              </p>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
