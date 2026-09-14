# Roadmap

## Phase 1 — Core (in progress)
- [x] Monorepo, config, logging, security, event bus
- [ ] LLM providers + model router with fallback
- [ ] Tool registry + core tools (shell, files, web, python)
- [ ] Agent loop with streaming and budgets
- [ ] REST + SSE chat API, session persistence

## Phase 2 — Autonomy
- [ ] Planner + orchestrator + task graph
- [ ] Specialist agent profiles (coder, researcher, reviewer, operator)
- [ ] Autonomous coding: repo clone, edit, test, PR
- [ ] Docker sandbox + PTY multi-terminal

## Phase 3 — Knowledge & control
- [ ] Memory store (episodic/semantic) + RAG over repos and docs
- [ ] Browser use (Playwright) with vision fallback
- [ ] Desktop control + Android (ADB) control
- [ ] Voice: STT commands, TTS responses, wake word

## Phase 4 — Product
- [ ] Next.js dashboard: chat, task graph, terminals, file diff viewer
- [ ] CLI `bhati` with interactive TUI
- [ ] MCP hub + plugin marketplace
- [ ] Auth, workspaces, quotas, billing hooks, admin panel

## Phase 5 — Scale
- [ ] Queue-based workers, autoscaling
- [ ] Postgres + pgvector, Redis cache
- [ ] Observability: traces, cost dashboards, evals/regression suite
