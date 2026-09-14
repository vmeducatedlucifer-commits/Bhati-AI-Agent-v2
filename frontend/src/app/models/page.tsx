"use client"

import { useCallback, useEffect, useState } from "react"
import { addCustomModel, deleteCustomModel, listModels, testModel } from "@/lib/swarm"
import { Button, Empty, Panel, Stat } from "@/components/ui/Primitives"
import { cx } from "@/lib/format"

type ModelInfo = {
  id: string
  type: string
  custom: boolean
  label?: string
  model?: string
  base_url?: string
  format?: string
}

const BUILTIN_HINT: Record<string, string> = {
  "builtin/gemini-2.0-flash": "General · fast · no API key needed",
  "builtin/gemini-1.5-pro": "Pro · deeper reasoning · no API key needed",
}

export default function ModelsPage() {
  const [data, setData] = useState<{
    providers: string[]
    models: ModelInfo[]
    defaults: Record<string, string>
  } | null>(null)
  const [result, setResult] = useState("")
  const [busy, setBusy] = useState<string | null>(null)
  const [form, setForm] = useState({
    alias: "",
    format: "openai",
    base_url: "",
    model: "",
    api_key: "",
    context_window: 128000,
    supports_tools: true,
  })

  const refresh = useCallback(async () => setData(await listModels()), [])
  useEffect(() => {
    refresh()
  }, [refresh])

  async function submit() {
    try {
      await addCustomModel(form)
      setResult(`✓ Added custom:${form.alias}`)
      setForm({ ...form, alias: "", base_url: "", model: "", api_key: "" })
      refresh()
    } catch (error) {
      setResult(String(error))
    }
  }

  const models = data?.models ?? []
  const builtins = models.filter((model) => model.id.startsWith("builtin"))
  const customs = models.filter((model) => model.custom)

  return (
    <div className="mx-auto flex h-full max-w-[1400px] flex-col gap-4 p-4 lg:p-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Providers" value={data?.providers.length ?? 0} hint="configured via env" />
        <Stat label="Models" value={models.length} tone="ok" />
        <Stat label="Custom endpoints" value={customs.length} hint="OpenAI / Anthropic compatible" tone="warn" />
        <Stat
          label="Built-in (keyless)"
          value={builtins.length || 2}
          hint="tunnel Gemini — works with zero keys"
        />
      </div>

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
        <Panel
          title="Add custom model"
          subtitle="Any OpenAI- or Anthropic-compatible endpoint, usable as custom:alias"
          bodyClassName="grid gap-2 p-4"
        >
          <input
            placeholder="alias (e.g. my-vllm)"
            value={form.alias}
            onChange={(event) => setForm({ ...form, alias: event.target.value })}
            className="input"
          />
          <select
            value={form.format}
            onChange={(event) => setForm({ ...form, format: event.target.value })}
            className="input"
          >
            <option value="openai">OpenAI-compatible (/chat/completions)</option>
            <option value="anthropic">Anthropic-compatible (/v1/messages)</option>
          </select>
          <input
            placeholder="base_url (http://localhost:8001/v1)"
            value={form.base_url}
            onChange={(event) => setForm({ ...form, base_url: event.target.value })}
            className="input"
          />
          <input
            placeholder="model id on the provider"
            value={form.model}
            onChange={(event) => setForm({ ...form, model: event.target.value })}
            className="input"
          />
          <input
            placeholder="api key (optional)"
            type="password"
            value={form.api_key}
            onChange={(event) => setForm({ ...form, api_key: event.target.value })}
            className="input"
          />
          <label className="flex items-center gap-2 px-1 text-xs text-[rgb(var(--muted))]">
            <input
              type="checkbox"
              checked={form.supports_tools}
              onChange={(event) => setForm({ ...form, supports_tools: event.target.checked })}
            />
            supports tool calling
          </label>
          <Button variant="primary" onClick={submit}>
            Save model
          </Button>
          {result && <p className="px-1 text-xs text-[rgb(var(--muted))]">{result}</p>}
        </Panel>

        <Panel
          title="Available models"
          subtitle={`defaults — ${Object.entries(data?.defaults ?? {})
            .map(([key, value]) => `${key}=${value}`)
            .join("  ·  ") || "loading…"}`}
          className="min-h-0"
          bodyClassName="space-y-2 p-3"
          actions={<Button onClick={refresh}>Refresh</Button>}
        >
          {!models.length && <Empty icon="◈" text="No models reported by the backend yet." />}
          {models.map((model) => {
            const builtin = model.id.startsWith("builtin")
            return (
              <div
                key={model.id}
                className={cx(
                  "flex flex-wrap items-center gap-2 rounded-xl border bg-black/25 px-3 py-2.5 text-sm transition",
                  builtin && "border-[rgb(var(--brand))]/40",
                )}
              >
                <span className="font-mono text-xs">{model.id}</span>
                {builtin && (
                  <span className="chip border border-[rgb(var(--ok))]/40 bg-[rgb(var(--ok))]/10 text-[rgb(var(--ok))]">
                    no API key
                  </span>
                )}
                {model.custom && (
                  <span className="chip border border-[rgb(var(--accent))]/40 bg-[rgb(var(--accent))]/10 text-[rgb(var(--accent))]">
                    {model.format}
                  </span>
                )}
                <span className="text-[11px] text-[rgb(var(--muted))]">
                  {BUILTIN_HINT[model.id] || model.label || model.model || model.type}
                </span>
                <div className="ml-auto flex gap-2">
                  <Button
                    className="text-xs"
                    disabled={busy === model.id}
                    onClick={async () => {
                      setBusy(model.id)
                      try {
                        setResult(JSON.stringify(await testModel(model.id)))
                      } catch (error) {
                        setResult(String(error))
                      } finally {
                        setBusy(null)
                      }
                    }}
                  >
                    {busy === model.id ? "Testing…" : "Test"}
                  </Button>
                  {model.custom && (
                    <Button
                      variant="danger"
                      className="text-xs"
                      onClick={() => deleteCustomModel(model.id.replace("custom:", "")).then(refresh)}
                    >
                      Remove
                    </Button>
                  )}
                </div>
              </div>
            )
          })}
        </Panel>
      </div>
    </div>
  )
}
