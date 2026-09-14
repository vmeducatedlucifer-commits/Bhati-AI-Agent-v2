# Custom AI models

Any OpenAI-compatible or Anthropic-compatible endpoint can be added at runtime -
no code change, no restart.

## Option 1 - runtime registry (recommended)

```bash
# OpenAI-compatible (vLLM, LM Studio, Together, Fireworks, Azure, a proxy...)
curl -X POST http://localhost:8000/api/models/custom -H 'content-type: application/json' -d '{
  "alias": "my-vllm",
  "format": "openai",
  "base_url": "http://localhost:8001/v1",
  "model": "Qwen2.5-72B-Instruct",
  "api_key": "",
  "context_window": 131072,
  "supports_tools": true
}'

# Anthropic-compatible gateway (LiteLLM, Bedrock proxy, custom relay)
curl -X POST http://localhost:8000/api/models/custom -H 'content-type: application/json' -d '{
  "alias": "claude-gw",
  "format": "anthropic",
  "base_url": "https://my-gateway.example.com/v1",
  "model": "claude-sonnet-4",
  "api_key": "sk-...",
  "headers": {"x-tenant": "bhati"}
}'
```

Use it anywhere a model is accepted: `custom:my-vllm`, `custom:claude-gw`
(chat, swarm launch, board tasks, per-agent overrides).

| Endpoint | Purpose |
|---|---|
| `GET /api/models` | providers + all models incl. custom |
| `GET /api/models/custom` | list custom models (keys masked) |
| `POST /api/models/custom` | add/update a custom model |
| `DELETE /api/models/custom/{alias}` | remove one |
| `POST /api/models/test` | one-shot smoke test of any model id |
| `POST /api/models/reload` | re-read providers + custom models |

Definitions persist to `CUSTOM_MODELS_FILE` (default `./data/custom_models.json`).

## Option 2 - single endpoint from .env

```env
CUSTOM_OPENAI_BASE_URL=http://localhost:8001/v1
CUSTOM_OPENAI_API_KEY=
CUSTOM_OPENAI_MODEL=Qwen2.5-72B-Instruct

CUSTOM_ANTHROPIC_BASE_URL=https://my-gateway.example.com
CUSTOM_ANTHROPIC_API_KEY=sk-...
CUSTOM_ANTHROPIC_MODEL=claude-sonnet-4
```

Address them as `custom-openai/<model>` and `custom-anthropic/<model>`, or set them as
the global default:

```env
DEFAULT_MODEL=custom:my-vllm
FAST_MODEL=custom:my-vllm
```

## Notes

- `format: openai` posts to `{base_url}/chat/completions` and supports tools, streaming and embeddings.
- `format: anthropic` posts to `{base_url}/v1/messages` (the `/v1` is added if missing) and sends
  both `x-api-key` and `Authorization: Bearer` so most gateways work out of the box.
- Set `supports_tools: false` for models without function calling - the swarm will still use them
  for research, critique and voting roles.
