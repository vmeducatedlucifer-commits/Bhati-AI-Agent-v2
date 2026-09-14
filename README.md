# 🧠 Bhati AI Agent v2

A professional, scalable, **multi-agent autonomous AI platform** — built from scratch.
Combines the strongest ideas from Claude Code, Codex, OpenCode, Manus and MiniMax Agent into one system:

- **Autonomous coding agent** — reads repos, edits code, runs tests, opens PRs
- **Multi-agent orchestration** — planner → specialists (coder / researcher / reviewer / operator) with a shared task graph
- **Computer & browser use** — sandboxed shell, headless/headful browser, desktop and Android device control
- **Multi-terminal dashboard** — many agents working in parallel, each with a live terminal
- **Long-term memory + RAG** — episodic, semantic and project memory
- **Voice control** — speech-to-text commands, text-to-speech replies
- **MCP native** — connect any Model Context Protocol server as tools
- **Any model** — OpenAI, Anthropic, Google, Groq, DeepSeek, Mistral, OpenRouter, Ollama (local)

## Architecture

```
bhati-ai-agent-v2/
├── backend/          FastAPI agent core (async, streaming, multi-tenant ready)
│   └── app/
│       ├── core/       config, logging, security, event bus
│       ├── llm/        provider abstraction + model router + fallbacks
│       ├── tools/      shell, files, web, browser, git, device, memory, mcp
│       ├── agents/     agent loop, planner, orchestrator, profiles, context
│       ├── memory/     vector store, RAG pipeline
│       ├── sandbox/    docker/local execution, PTY terminals
│       ├── mcp/        MCP client manager
│       ├── db/         SQLAlchemy models (SQLite dev → Postgres prod)
│       └── api/        REST + SSE + WebSocket routes
├── frontend/         Next.js dashboard (chat, task graph, terminals, files, settings)
├── cli/              `bhati` terminal client (Claude Code style)
├── sandbox/          execution sandbox image
├── deploy/           Render, Docker, Compose, Fly configs
└── docs/             architecture, roadmap, API, self-hosting
```

## Design principles

1. **Deployable anywhere** — one Docker Compose locally, one click on Render, horizontally scalable in prod.
2. **SaaS-ready from day one** — workspaces, users, API keys, quotas, usage metering, row-level isolation.
3. **Provider agnostic** — no vendor lock-in; model routing by cost/latency/capability.
4. **Safe by default** — every dangerous tool call passes an approval policy engine.
5. **Observable** — structured logs, traces, token/cost accounting on every step.

## Quick start

```bash
cp backend/.env.example backend/.env   # add at least one provider API key
docker compose up --build              # API :8000, Web :3000
```

Local (no Docker):

```bash
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

## Deploy on Render

The repo ships a `render.yaml` blueprint: API web service + static/Node web frontend + Postgres + Redis.
Push to GitHub → Render → *New Blueprint* → select this repo.

## Status

Active rebuild. See `docs/ROADMAP.md` for phases.

## License

MIT
