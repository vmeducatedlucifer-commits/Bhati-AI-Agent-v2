# Agent-to-Agent Graph View

Live picture of **who is talking to whom** inside a swarm. Open `/swarm` and use the
`Split | Graph | Feed` switch in the control bar.

## What you see

| Element | Meaning |
| --- | --- |
| Node | An agent. Size grows with how much it talks, colour = live status (green working, yellow waiting, orange blocked, red failed, blue done, grey idle). |
| Big labelled node | `queen` (planner) or a team lead. |
| Indigo node | A topic hub (`team:build`, `leads`, `debate`) — broadcasts flow through it instead of drawing n² edges. |
| Edge thickness | Number of messages exchanged in that direction. |
| Edge colour | Kind of the most recent message (proposal, critique, vote, request, handoff, help, result…). |
| Slow drifting dots | Ambient traffic volume on that link. |
| Bright glowing dot | A message that arrived **just now** over SSE. |
| Expanding ring on a node | That agent just sent or received something. |

Curved edges mean `A → B` and `B → A` are drawn separately, so request/response
pairs are visible instead of overlapping.

## Interaction

- **Hover** a node: role, team, status, sent/received counts, current action.
- **Click** a node: focus mode — everything unrelated dims, and the conversation
  feed filters to that agent. Click again (or *clear focus*) to reset.
- **Time window** `all / 1m / 5m / 15m`: only count recent traffic, so you can see
  what the swarm is doing *right now* rather than cumulative history.
- **broadcasts** toggle: hide topic hubs to see only direct agent-to-agent talk.

## Reading the swarm's health

- **Top talkers** (bottom-left) — if one agent dominates, it is a bottleneck; raise
  team size or split its role.
- **Isolated agents** — registered but never spoke. Usually means the planner did not
  hand them work, or they are blocked waiting for the blackboard.
- **Density** — very high density at large sizes means chatter overhead; reduce
  cross-team broadcasts or rely more on the blackboard.

## Scale behaviour

Rendering is plain canvas with a sampled force simulation, so it stays smooth at
60fps. Above **260 nodes** the view automatically collapses workers into team hubs
(`build ×180`), keeping leads, the queen and topics explicit — this is how a
1200-agent run stays readable. Zoom back in by lowering the swarm size or focusing
a single team.

## API

```http
GET /api/swarm/graph/{session_id}?window=60&include_broadcasts=true&limit=4000
```

```jsonc
{
  "nodes": [{ "id": "build-1", "type": "agent", "team": "build", "status": "working", "degree": 12 }],
  "edges": [{ "source": "build-lead", "target": "build-1", "count": 7, "last_kind": "request" }],
  "stats": { "node_count": 42, "edge_count": 96, "density": 0.055, "hubs": [], "isolated": [] }
}
```

Poll it every ~2.5s for layout; the bright live pulses come from the existing SSE
stream `GET /api/swarm/stream/{session_id}`.
