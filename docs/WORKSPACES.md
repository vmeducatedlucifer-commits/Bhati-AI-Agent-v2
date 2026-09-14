# Agent workspaces

Every session gets its own folder on disk; every agent in a swarm gets a private
home inside it. Everything an agent writes is browsable and downloadable from the
UI (`/workspace`).

## Layout

```
<WORKSPACE_DIR>/<session_id>/            <- main agent's root + tool sandbox
  agents/<agent_id>/                     <- private home, one per swarm agent
  shared/                                <- cross-agent deliverables
  downloads/                             <- final artifacts for the user
```

- `WORKSPACE_DIR` defaults to `./workspaces` locally and `/tmp/workspaces` on
  Render free tier (`EPHEMERAL_WORKSPACE=true`, wiped on restart — download
  what you need).
- The tool sandbox for every agent is the **session** root, so agents can read
  each other's work; `ToolContext.resolve` blocks anything outside it.
- Each agent is told in its system prompt: private folder, `shared/`,
  `downloads/`, and that artifacts must be written to real files.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/workspace` | all session workspaces |
| GET | `/api/workspace/{session}` | stats + per-agent folders |
| GET | `/api/workspace/{session}/tree?path=&agent_id=&depth=` | file tree |
| GET | `/api/workspace/{session}/file?path=` | text preview + metadata |
| GET | `/api/workspace/{session}/download?path=` | download a single file |
| GET | `/api/workspace/{session}/archive?path=&agent_id=` | zip a folder / session |
| POST | `/api/workspace/{session}/upload?path=` | upload a file for the agents |
| DELETE | `/api/workspace/{session}/file?path=` | delete a file or folder |

## UI

`/workspace` gives you: session picker, per-agent folder list with file counts
and sizes, lazy file tree, code/text preview, single-file download, one-click
`.zip` export (whole session, one agent, or just `downloads/`), upload, delete,
and 10s auto-refresh so files appear live while the swarm works.
