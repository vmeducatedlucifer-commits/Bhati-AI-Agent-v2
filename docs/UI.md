# UI (v2.2)

Completely rebuilt frontend — Next.js App Router + Tailwind with a custom
design system (no more plain zinc boxes).

## Design system

- `frontend/src/app/globals.css` — CSS-variable tokens (`--brand`, `--brand-2`,
  `--panel`, `--ok/--warn/--err`), glass panels, gradient buttons, grid/aurora
  background, thin scrollbars and animations (`animate-ring`, `float-in`,
  `edge-flow`, `shimmer`, `text-gradient`).
- `frontend/src/components/ui/Primitives.tsx` — `Panel`, `Stat`, `Badge`,
  `Button`, `Empty`, `Spinner`.
- `frontend/src/components/shell/AppShell.tsx` — icon nav rail, top bar with
  live backend health + provider count + version, and a ⌘K command palette
  (`CommandPalette.tsx`).
- `frontend/src/lib/client.ts` — typed API client (health, models, workspace,
  swarm, SSE events, streaming chat). `frontend/src/lib/format.ts` — bytes,
  relative time, file icons, status colors, `cx`.

## Pages

| Route | What you get |
| --- | --- |
| `/` | Cockpit: main-agent chat (streaming), model picker, live event feed, session stat cards, artifact shortcuts + one-click zip |
| `/swarm` | Swarm control bar (1–1200 agents), animated agent-to-agent graph, live conversation with kind filters, agent mesh, blackboard, plan, workspace downloads |
| `/workspace` | Session picker, per-agent folders with file counts/sizes, file tree, text/code preview, single-file download, zip export, upload, delete |
| `/tasks` | 5-column board, task composer (mode/size/assignee/priority/model), detail drawer with activity log, per-agent file download |
| `/models` | Providers and custom models, including the keyless built-in Gemini models |

Set `NEXT_PUBLIC_API_URL` to the backend URL (e.g.
`https://bhati-api.onrender.com`); it defaults to `http://localhost:8000`.
