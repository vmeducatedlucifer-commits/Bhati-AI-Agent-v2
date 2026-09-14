# Built-in AI model (keyless)

Bhati-AI-Agent-v2 ships with an **inbuilt model** ported from v1's `gateway`
tunnel. It works with **no API key, no cookie, no account** — if nothing else is
configured, the agent still thinks, plans and calls tools.

| Alias    | Model id            | Router spec                   |
| -------- | ------------------- | ----------------------------- |
| General  | `gemini-2.0-flash`  | `builtin/gemini-2.0-flash`    |
| Pro      | `gemini-1.5-pro`    | `builtin/gemini-1.5-pro`      |

## How it works

```
agent loop -> ModelRouter -> BuiltinProvider -> GeminiTunnel
                                                 |- official REST API (only if GEMINI_API_KEY set)
                                                 |- keyless web tunnel (default)
```

- `app/gateway/tunnel.py` emulates a real Chrome session: it warms up
  `gemini.google.com/app`, scrapes the build label (`cfb2h`), stream id
  (`FdrFJe`) and `at` token (`SNlM0e`), then posts the 102-element
  `StreamGenerate` payload.
- TLS fingerprinting uses `curl_cffi` when installed, else plain `httpx`.
- A pool of warm sessions (default 5) rotates per request, with cooldown and
  quarantine on HTTP 429/403/401/503, HTML/consent pages, or empty responses.
- Unlike v1 there is **no loopback gateway server and no shared secret** — the
  tunnel runs in-process, so Render free tier (single port, single worker) is
  fine.

## Tool calling

The tunnel returns plain text, so tools are injected as a Hermes-style system
prompt (`app/gateway/tools.py`) and parsed back out of the reply
(`<tool_call>`, `<tool_use>`, or fenced JSON). Streaming holds back text from
the first marker so raw XML never reaches the UI.

## Routing rules

1. `builtin` / `builtin/<model>` → always the built-in model.
2. bare `gemini-2.0-flash` / `gemini-1.5-pro` → built-in **unless**
   `GOOGLE_API_KEY` is set (then the official Google provider wins).
3. Any unknown or unconfigured provider falls back down the chain and ends at
   `builtin`, so `No LLM provider configured` can no longer happen.

Make it the default everywhere:

```env
DEFAULT_MODEL=builtin/gemini-2.0-flash
FAST_MODEL=builtin/gemini-2.0-flash
REASONING_MODEL=builtin/gemini-1.5-pro
```

## Optional environment variables

All optional — defaults work keyless.

| Variable | Default | Purpose |
| --- | --- | --- |
| `BUILTIN_MODEL_ENABLED` | `1` | `0` disables the built-in provider |
| `BUILTIN_DEFAULT_MODEL` | `gemini-2.0-flash` | model used when none given |
| `GEMINI_API_KEY` | — | comma-separated official keys, tried first |
| `GEMINI_COOKIE` | — | one or more cookie strings (`\|\|\|` separated) for higher limits |
| `GEMINI_SAPISID` / `GEMINI_AT` | — | manual auth tokens |
| `STREAM_BL` | auto | build label override |
| `SESSION_POOL_SIZE` | `5` | warm sessions kept alive |
| `ROTATE_SESSION` | `1` | rotate session on every request |
| `MAX_REQUESTS_PER_SESSION` | `15` | retire a session after N calls |
| `SESSION_COOLDOWN_SECONDS` | `60` | quarantine length after a block |
| `MAX_RETRIES` | `3` | session rotations per request |
| `REQUEST_TIMEOUT` | `180` | upstream timeout (seconds) |
| `UPSTREAM_PROXY` | — | proxy for tunnel traffic |
| `BROWSER_IMPERSONATE` | `chrome124` | curl_cffi fingerprint |
| `BUILTIN_PREWARM_SESSIONS` | `1` | sessions warmed at boot |

## Limits

- Unofficial endpoint: Google can change it; expect occasional rotation churn.
  Add cookies or an official key for heavier usage.
- No embeddings — vector memory still needs an embedding provider (or falls
  back to keyword search).
- No image input via the tunnel.
- On free Render, cold starts add ~10–20s for the first warm-up.

## Verify

```bash
curl https://bhati-api.onrender.com/api/models          # should list builtin + gemini ids
curl -X POST https://bhati-api.onrender.com/api/chat \
  -H 'content-type: application/json' \
  -d '{"message":"hello, who are you?","model":"builtin/gemini-2.0-flash"}'
```
