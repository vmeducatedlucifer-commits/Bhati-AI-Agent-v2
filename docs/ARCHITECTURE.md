# Architecture

## 1. Runtime overview

```
           ┌────────────┐   SSE / WS   ┌──────────────────────────┐
 Web UI ──▶│  API layer │◀────────────▶│  Orchestrator (supervisor)│
 CLI  ────▶│ FastAPI    │              └────────────┬─────────────┘
 Bot  ────▶└─────┬──────┘                           │ spawns
                 │                       ┌──────────▼───────────┐
                 │                       │  Agent workers       │
                 │                       │  planner / coder /   │
                 │                       │  researcher / ops    │
                 │                       └──────────┬───────────┘
           ┌─────▼───────┐   tool calls             │
           │  Event bus  │◀─────────────────────────┤
           └─────┬───────┘                          │
     ┌───────────┼─────────────┬────────────┬───────┴──────┐
  LLM router  Tool registry  Memory/RAG   Sandbox        MCP hub
```

## 2. Core abstractions

| Abstraction | Responsibility |
|---|---|
| `LLMProvider` | Uniform chat + tool-calling + streaming across vendors |
| `ModelRouter` | Chooses model by task class, cost, latency; automatic fallback |
| `Tool` | Typed JSON-schema tool with permission level and audit hooks |
| `ToolRegistry` | Discovery, filtering per agent profile, MCP tool injection |
| `AgentLoop` | ReAct loop: think → call tools → observe → repeat, with budgets |
| `Orchestrator` | Task graph, sub-agent spawning, parallelism, result merging |
| `MemoryStore` | Episodic (sessions), semantic (embeddings), project notes |
| `Sandbox` | Isolated execution: local subprocess or Docker container, PTY |
| `EventBus` | Streams every token/tool/step to all subscribed surfaces |

## 3. Execution model

1. Request arrives with a goal and a session id.
2. Planner decomposes the goal into a DAG of tasks with acceptance criteria.
3. Orchestrator schedules ready tasks onto agent workers (bounded concurrency).
4. Each worker runs an `AgentLoop` with a scoped tool set and its own terminal.
5. Every step emits events → persisted + streamed to the UI.
6. Reviewer agent verifies acceptance criteria; failures are re-queued with feedback.
7. Result, artifacts and memories are written back to storage.

## 4. Safety

- Permission levels: `safe`, `write`, `dangerous`, `system`.
- Policy engine decides: auto-allow / ask user / deny; configurable per workspace.
- All shell and device actions run inside the sandbox with resource limits.
- Secret scanning on any content before it leaves the workspace.

## 5. Scaling & SaaS

- Stateless API pods behind a load balancer; sessions in Postgres, cache in Redis.
- Agent workers can run in-process (dev) or as queue consumers (prod).
- Multi-tenancy: `workspace_id` on every row; API keys scoped per workspace.
- Metering: tokens, tool calls, sandbox seconds recorded per workspace for billing.
