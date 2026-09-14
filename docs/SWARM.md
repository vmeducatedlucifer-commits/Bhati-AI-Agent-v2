# Swarm architecture (up to 1200 agents)

## Topology

```
                user goal / board task
                          |
                       [QUEEN]              decomposes -> plan DAG, forms teams,
                     /    |     \           resolves conflicts, synthesises output
            [research] [build] [verify] [ops]     <- team LEADS (topic: leads)
              / | \     / | \    / | \    / | \
            workers    workers  workers  workers  <- do tool work (topic: team:<name>)

   shared channels:  A2A bus (messages)  +  blackboard (knowledge)
```

## Why it scales to 1200

| Concern | Solution |
|---|---|
| 1200 OS threads/processes | Agents are **coroutines**; one event loop, ~KBs each |
| LLM rate limits | `swarm_llm_concurrency` semaphore caps **in-flight model calls**, separate from agent count |
| O(n^2) chatter | Agents talk on **team topics**; only leads talk cross-team (`leads` topic) |
| Slow task blocking others | **Work-stealing** priority queue - any free worker pulls the next ready task |
| Memory blow-up | Bounded inboxes (drop-oldest), bounded message ring buffer, bounded task queue |
| Duplicate work | Shared **blackboard** - agents read what others already found before acting |
| Disagreement | **Debate protocol**: propose -> critique -> vote -> decision recorded on the blackboard |

## Message kinds (what you see in the live feed)

`chat`, `request`, `response`, `proposal`, `critique`, `vote`, `handoff`, `status`, `help`, `announce`, `result`

## Tools agents use to coordinate

| Tool | Purpose |
|---|---|
| `swarm_say` | broadcast to the team/topic |
| `swarm_ask` | direct question to a named agent, waits for reply |
| `swarm_inbox` | read incoming messages |
| `swarm_roster` | see who exists, their role, team and status |
| `blackboard_post` | publish a fact / artifact / risk / decision |
| `blackboard_read` | search shared knowledge before redoing work |
| `swarm_debate` | force a structured argument and get consensus |

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/swarm/launch` | start a swarm (`goal`, `size` up to 1200, `model`, custom `teams`) |
| `GET /api/swarm/snapshot/{session}` | one-shot dashboard state (agents, messages, blackboard, runs) |
| `GET /api/swarm/stream/{session}` | **SSE live feed of every agent-to-agent message** |
| `GET /api/swarm/agents/{session}` | roster + status/role/team rollups |
| `GET /api/swarm/messages/{session}` | message history, filterable by topic/agent |
| `GET /api/swarm/blackboard/{session}` | shared knowledge entries |
| `POST /api/swarm/debate` | run a debate on demand |
| `POST /api/swarm/runs/{id}/cancel` | stop everything |

## Tuning

```env
SWARM_MAX_AGENTS=1200        # hard ceiling
SWARM_DEFAULT_AGENTS=12      # used when size is not given
SWARM_LLM_CONCURRENCY=24     # the real throughput knob
SWARM_AGENT_MAX_STEPS=15     # per-worker step cap
SWARM_DEBATE_ROUNDS=1
```

Rule of thumb: `agents` can be large, but keep `SWARM_LLM_CONCURRENCY` at or below your
provider's rate limit. On Render free tier use `SWARM_MAX_AGENTS<=50` and `LLM_CONCURRENCY<=4`.
