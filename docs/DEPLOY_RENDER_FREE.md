# Deploy on Render - FREE tier (no disk)

Free plan pe persistent disk nahi milti. Isliye v2 ko is tarah chalaya jata hai:

| Cheez | Free tier me kahan | Persist hota hai? |
|---|---|---|
| Sessions, messages, runs, audit | Free Postgres | Haan |
| Long-term memory / RAG index | Postgres-backed store | Haan |
| Agent workspace (cloned repos, generated files) | `/tmp/workspaces` | Nahi (restart pe clear) |
| Terminals | in-process PTY | Nahi |

Matlab: **kaam ka record safe rehta hai, kaam ki files temporary hain.** Isliye agent ko
bolo ki output GitHub pe push kare ya file download kar lo - wahi "persistence" hai.

## Steps

1. Render dashboard -> **New +** -> **Blueprint** -> ye repo select karo.
2. Render `render.yaml` padhkar 3 cheezein banayega: `bhati-api` (Docker, free),
   `bhati-web` (Node, free), `bhati-db` (Postgres, free).
3. Deploy ke baad `bhati-api` -> **Environment** me apni keys daalo
   (kam se kam ek): `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` /
   `OPENROUTER_API_KEY` / `GROQ_API_KEY`.
4. Health check: `https://<your-api>.onrender.com/api/health`

## Free tier ki limits aur unka jugaad

- **512 MB RAM / 0.1 CPU** -> blueprint me `MAX_PARALLEL_AGENTS=2`, `MAX_STEPS=25`,
  `WEB_CONCURRENCY=1` set hai. Isse zyada parallel agents free plan pe OOM karenge.
- **15 min idle pe sleep** -> pehli request 30-60s leti hai. SSE stream shuru hone se
  pehle cold start hota hai, ye normal hai.
- **Koi disk nahi** -> `WORKSPACE_DIR=/tmp/workspaces`. Restart pe files chali jayengi.
  Important output ke liye agent se bolo: `git_push` / `open_pull_request` karo,
  ya dashboard ke Files tab se download kar lo.
- **Docker-in-Docker nahi** -> `SANDBOX_MODE=local` (commands API container ke andar
  hi chalti hain). Sirf apne liye use karo; public/multi-user ke liye paid + Docker sandbox.
- **Free Postgres ~30 din** me expire hota hai - naya bana kar `DATABASE_URL` update kar do,
  ya Neon/Supabase ka free Postgres use karo (wo expire nahi hota).
- **Playwright/browser tools** free RAM me bhari padte hain - browser wale kaam locally chalao.

## Behtar free setup (recommended)

- **Backend**: Render free (Docker)
- **Database**: Neon free Postgres (`DATABASE_URL` manually set karo, blueprint wali db hata do)
- **Frontend**: Vercel free (`frontend/vercel.json` ready hai) - `NEXT_PUBLIC_API_URL` me
  apna Render API URL daalo. Isse ek Render free service bach jati hai aur dashboard sota nahi.
- **Models**: Groq ya OpenRouter ke free/sasta models - `DEFAULT_MODEL=groq/llama-3.3-70b-versatile`

## Sleep se bachne ka tareeka

Kisi free cron (cron-job.org / UptimeRobot) se har 10 min pe
`https://<your-api>.onrender.com/api/health` hit karwa do. Free plan pe monthly
instance-hours limited hain, isliye sirf tab karo jab active use kar rahe ho.
