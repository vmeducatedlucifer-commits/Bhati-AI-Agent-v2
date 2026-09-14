# Turning Bhati into a SaaS

The v2 architecture is already multi-tenant-shaped. What is in place:

- **Stateless API** - scale horizontally behind a load balancer; sessions live in Postgres.
- **Per-session workspaces** - `WORKSPACE_DIR/<session_id>`, path-escape protected.
- **JWT auth hook** - `AUTH_ENABLED=true` plus `app/api/deps.py:current_user`.
- **Container sandbox** - `SANDBOX_MODE=docker` isolates all code execution.
- **Usage accounting** - every LLM call returns `Usage`; tool calls are audited in `tool_audit`.
- **Event bus** - swap the in-memory bus for Redis pub/sub to stream across replicas.

## Remaining work for production SaaS

1. **Tenancy**: add `org_id` to `sessions`, `runs`, `tool_audit`; filter every query by it.
2. **Billing**: meter `Usage.total_tokens` + sandbox minutes per org; Stripe metered subscriptions.
3. **Quotas**: per-plan caps on `max_steps`, `max_parallel_agents`, concurrent terminals.
4. **Isolation**: one Firecracker/gVisor microVM (or Fly Machine) per org instead of shared Docker.
5. **Secrets**: move provider keys and MCP credentials to a vault, encrypted per org (BYO-key supported).
6. **Observability**: OpenTelemetry traces per run, plus Sentry for errors.
7. **Compliance**: audit log export, data retention policy, workspace wipe on cancellation.

## Suggested plan tiers

| Tier | Parallel agents | Sandbox | Retention |
|---|---|---|---|
| Free | 1 | shared, 5 min timeout | 7 days |
| Pro | 4 | dedicated container | 90 days |
| Team | 8+ | microVM per org | 1 year + export |
