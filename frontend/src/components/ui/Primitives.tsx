"use client";

import { ReactNode } from "react";
import { cx } from "@/lib/format";

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cx("glass glass-hover flex min-h-0 flex-col", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="truncate text-sm font-semibold tracking-tight">{title}</h2>}
            {subtitle && (
              <p className="truncate text-xs text-[rgb(var(--muted))]">{subtitle}</p>
            )}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx("min-h-0 flex-1 overflow-auto scroll-thin p-4", bodyClassName)}>
        {children}
      </div>
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone = "brand",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "brand" | "ok" | "warn" | "err";
}) {
  const tones: Record<string, string> = {
    brand: "from-[rgb(var(--brand))]/25 to-transparent",
    ok: "from-[rgb(var(--ok))]/20 to-transparent",
    warn: "from-[rgb(var(--warn))]/20 to-transparent",
    err: "from-[rgb(var(--err))]/20 to-transparent",
  };
  return (
    <div className="glass relative overflow-hidden p-4">
      <div className={cx("pointer-events-none absolute inset-0 bg-gradient-to-br", tones[tone])} />
      <p className="relative text-[11px] uppercase tracking-wider text-[rgb(var(--muted))]">
        {label}
      </p>
      <p className="relative mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="relative mt-1 text-xs text-[rgb(var(--muted))]">{hint}</p>}
    </div>
  );
}

export function Badge({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <span className={cx("chip border", className)}>{children}</span>;
}

export function Button({
  children,
  onClick,
  variant = "ghost",
  disabled,
  title,
  className,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "ghost" | "danger";
  disabled?: boolean;
  title?: string;
  className?: string;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={cx("btn", `btn-${variant}`, className)}
    >
      {children}
    </button>
  );
}

export function Empty({ icon = "✨", text }: { icon?: string; text: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 py-10 text-center">
      <span className="text-3xl opacity-70">{icon}</span>
      <p className="max-w-xs text-sm text-[rgb(var(--muted))]">{text}</p>
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-xs text-[rgb(var(--muted))]">
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/20 border-t-[rgb(var(--brand-2))]" />
      {label}
    </div>
  );
}
