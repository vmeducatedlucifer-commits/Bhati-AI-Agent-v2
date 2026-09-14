# Self-hosting Bhati AI Agent v2

## 1. Local (fastest)

```bash
git clone https://github.com/vmeducatedlucifer-commits/Bhati-AI-Agent-v2
cd Bhati-AI-Agent-v2
make setup                      # backend venv + frontend deps + .env
# add at least one provider key in backend/.env
make dev                        # API :8000 + dashboard :3000
```

Minimum `.env`:

```env
OPENAI_API_KEY=sk-...           # or ANTHROPIC_API_KEY / GOOGLE_API_KEY / OPENROUTER_API_KEY
DEFAULT_MODEL=anthropic/claude-sonnet-4
SANDBOX_MODE=local
```

Fully offline option: run Ollama and set `DEFAULT_MODEL=ollama/qwen2.5-coder:14b`.

## 2. Docker Compose (recommended for a server)

```bash
cp backend/.env.example backend/.env
make sandbox-image              # build the execution sandbox
docker compose up --build -d    # api :8000, web :3000, postgres, redis
```

With `SANDBOX_MODE=docker` every shell/python tool call runs inside a disposable
`bhati-sandbox` container with the session workspace mounted.

## 3. Render (one click)

The repo ships `render.yaml`. In Render: **New > Blueprint**, point at this repo.
It provisions the API (Docker + 10 GB disk for workspaces), the Next.js dashboard,
and a managed Postgres. Add provider keys as secrets after the first deploy.

> On Render use `SANDBOX_MODE=local` (no Docker-in-Docker). For untrusted
> multi-tenant workloads, run the sandbox on a separate VM/Fly machine.

## 4. Android / desktop control

- Android: install `adb`, enable USB debugging, then `android_devices` / `android_action` tools work.
- Desktop: the `desktop_action` tool needs a display; on servers run under Xvfb.
- Browser: Playwright runs headless by default — `playwright install chromium`.

## 5. Production checklist

- `AUTH_ENABLED=true` and a strong `JWT_SECRET`
- Postgres (not SQLite) via `DATABASE_URL`
- Restrict `CORS_ORIGINS` to your dashboard domain
- Keep `SANDBOX_MODE=docker` for anything untrusted
- Persistent volume for `WORKSPACE_DIR`
