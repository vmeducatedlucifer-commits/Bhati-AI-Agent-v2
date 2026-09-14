export function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${value >= 10 || index === 0 ? Math.round(value) : value.toFixed(1)} ${units[index]}`;
}

export function timeAgo(epochSeconds: number): string {
  if (!epochSeconds) return "-";
  const seconds = Math.max(1, Math.floor(Date.now() / 1000 - epochSeconds));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function fileIcon(name: string): string {
  const ext = name.split(".").pop()?.toLowerCase() || "";
  const map: Record<string, string> = {
    py: "🐍", js: "📜", ts: "📘", tsx: "⚛️", jsx: "⚛️", json: "🧾", md: "📝",
    txt: "📄", csv: "📊", xlsx: "📊", pdf: "📕", zip: "🗜️", png: "🖼️",
    jpg: "🖼️", jpeg: "🖼️", svg: "🖼️", gif: "🖼️", html: "🌐", css: "🎨",
    sh: "⌨️", yml: "⚙️", yaml: "⚙️", sql: "🗄️", log: "📃",
  };
  return map[ext] || "📄";
}

export function statusColor(status: string): string {
  switch (status) {
    case "working":
    case "running":
      return "text-[rgb(var(--brand-2))] border-[rgb(var(--brand-2))]/40 bg-[rgb(var(--brand-2))]/10";
    case "done":
    case "completed":
      return "text-[rgb(var(--ok))] border-[rgb(var(--ok))]/40 bg-[rgb(var(--ok))]/10";
    case "failed":
    case "error":
      return "text-[rgb(var(--err))] border-[rgb(var(--err))]/40 bg-[rgb(var(--err))]/10";
    case "waiting":
    case "pending":
      return "text-[rgb(var(--warn))] border-[rgb(var(--warn))]/40 bg-[rgb(var(--warn))]/10";
    default:
      return "text-[rgb(var(--muted))] border-white/10 bg-white/5";
  }
}

export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}
