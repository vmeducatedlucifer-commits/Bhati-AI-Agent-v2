"use client"

export default function SwarmError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="glass max-w-lg p-6 text-center">
        <h2 className="text-lg font-semibold">Swarm dashboard could not render</h2>
        <p className="mt-2 text-sm text-[rgb(var(--muted))]">
          The backend returned data this view did not expect, or it is unreachable. The UI stays
          alive — retry after the API wakes up.
        </p>
        <pre className="mt-4 max-h-40 overflow-auto scroll-thin rounded-xl border bg-black/40 p-3 text-left text-xs">
          {error.message}
          {error.digest ? `\n\ndigest: ${error.digest}` : ""}
        </pre>
        <div className="mt-4 flex justify-center gap-2">
          <button onClick={reset} className="btn btn-primary text-sm">
            Retry
          </button>
          <a href="/" className="btn btn-ghost text-sm">
            Back to cockpit
          </a>
        </div>
      </div>
    </div>
  )
}
