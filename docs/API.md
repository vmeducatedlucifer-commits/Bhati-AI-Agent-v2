# HTTP API

Base: `http://localhost:8000/api` - interactive docs at `/docs`.

## System
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/info` | providers, models, tool count, sandbox mode |

## Chat & runs
| Method | Path | Purpose |
|---|---|---|
| POST | `/chat` | single-shot reply |
| POST | `/chat/stream` | SSE: deltas, tool calls, plan/task updates |
| POST | `/runs` | start an autonomous multi-agent run |
| GET | `/runs`, `/runs/{id}` | inspect runs and the task graph |
| POST | `/runs/{id}/cancel` | cancel a run and its workers |
| GET | `/events/{session_id}` | global SSE feed for the dashboard |

```bash
curl -N -X POST localhost:8000/api/chat/stream \
  -H 'content-type: application/json' \
  -d '{"message":"list files and summarise the repo","mode":"chat","profile":"coder"}'
```

SSE event types: `session`, `message_delta`, `thinking`, `tool_call`, `tool_result`,
`plan_created`, `task_updated`, `agent_start`, `agent_end`, `usage`, `final`, `error`, `done`.

## Sessions, tools, files
| Method | Path | Purpose |
|---|---|---|
| POST/GET/DELETE | `/sessions` | session CRUD |
| GET | `/sessions/{id}/messages` | history |
| GET | `/tools` | tool catalogue with JSON schemas |
| POST | `/tools/invoke` | run one tool directly |
| GET | `/files/tree`, `/files/read`, `/files/download` | workspace browsing |
| POST | `/files/upload` | upload into the session workspace |

## Terminals, voice, MCP
| Method | Path | Purpose |
|---|---|---|
| POST/GET/DELETE | `/terminals` | spawn, list, kill PTY sessions |
| WS | `/terminals/ws/{id}` | live terminal I/O |
| POST | `/voice/transcribe`, `/voice/speak`, `/voice/command` | STT, TTS, spoken commands |
| GET/POST | `/mcp/servers` | connect MCP servers; their tools hot-register |

When `AUTH_ENABLED=true`, send `Authorization: Bearer <jwt>`.
