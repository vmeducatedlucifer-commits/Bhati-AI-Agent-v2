# Render deploy troubleshooting

Most free-tier failures fall into one of the cases below. Find your log line, apply the fix.

## 1. Service builds, then dies instantly (most common)

```
sqlalchemy.exc.InvalidRequestError: The asyncio extension requires an async driver to be used.
The loaded 'psycopg2' is not async.
```

**Cause:** Render's `DATABASE_URL` is `postgresql://...` (sync driver) but the app uses an async engine.

**Fixed in the code now** — `DATABASE_URL` is auto-rewritten to `postgresql+asyncpg://` and libpq-only
args (`sslmode`, `channel_binding`) are stripped. Just redeploy the latest `main`.

## 2. Blueprint fails to parse / "invalid envVar"

`fromService: ... envVarKey: RENDER_EXTERNAL_URL` is **not** allowed — `RENDER_EXTERNAL_URL` is
runtime-injected, not a declared env var. It is removed from `render.yaml`.

**Do this instead:** after `bhati-api` deploys, open `bhati-web` → Environment → set
`NEXT_PUBLIC_API_URL = https://bhati-api.onrender.com` (no trailing slash) → **Clear build cache & deploy**.
Next.js inlines `NEXT_PUBLIC_*` at build time, so a redeploy is required.

## 3. Health check fails / "Timed out waiting for service to become available"

- Health path must be `/api/health` (set in the blueprint).
- The server must bind `0.0.0.0:$PORT`. Render injects `PORT`; the Dockerfile CMD must use it:
  `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`.
- Free instances cold-start in 30–60s. Raise nothing else; just wait out the first boot.

## 4. `Read-only file system` or `PermissionError: './workspaces'`

Free services have no disk. `WORKSPACE_DIR=/tmp/workspaces` is set in the blueprint, and the code now
falls back to `/tmp/workspaces` automatically if the configured path is not writable.

## 5. Out of memory / SIGKILL (exit 137)

512 MB is tight. Keep:

```
WEB_CONCURRENCY=1
MAX_PARALLEL_AGENTS=2
SWARM_MAX_AGENTS=50
SWARM_LLM_CONCURRENCY=4
```

A 1200-agent swarm will **not** fit on free tier — run that locally or on a paid instance.

## 6. Docker build fails on `docker` / sandbox deps

Free tier cannot run Docker-in-Docker. `SANDBOX_MODE=local` must stay set; do not switch to `docker`.

## 7. Frontend loads but every API call fails (CORS / network error)

- `NEXT_PUBLIC_API_URL` missing or has a trailing slash → fix and redeploy with cache cleared.
- API asleep → first request after idle takes ~50s; retry once.
- `CORS_ORIGINS=*` is already set on the API.

## 8. `No LLM provider configured`

Add at least one key to **bhati-api → Environment**: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`OPENROUTER_API_KEY`, or `GROQ_API_KEY`. Then set `DEFAULT_MODEL` to a model that key can serve,
e.g. `openai/gpt-4o-mini` or `custom:my-endpoint`.

## Quick self-check after deploy

```bash
curl https://bhati-api.onrender.com/api/health
curl https://bhati-api.onrender.com/api/info        # providers, tools, sandbox mode
curl https://bhati-api.onrender.com/api/swarm/config
```

If `/api/health` answers but `/api/info` shows `providers: []`, the deploy is fine — you only need keys.
