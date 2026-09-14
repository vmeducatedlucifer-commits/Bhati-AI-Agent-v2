"use client"

import { useCallback, useEffect, useState } from "react"
import { addCustomModel, deleteCustomModel, listModels, testModel } from "@/lib/swarm"

type ModelInfo = { id: string; type: string; custom: boolean; label?: string; model?: string; base_url?: string; format?: string }

export default function ModelsPage() {
  const [data, setData] = useState<{ providers: string[]; models: ModelInfo[]; defaults: Record<string, string> } | null>(null)
  const [result, setResult] = useState<string>("")
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
      setResult(`Added custom:${form.alias}`)
      refresh()
    } catch (error) {
      setResult(String(error))
    }
  }

  return (
    <main className="min-h-screen bg-zinc-950 p-6 text-zinc-100">
      <h1 className="text-lg font-semibold">Models</h1>
      <p className="mt-1 text-xs text-zinc-500">
        Add any OpenAI-compatible or Anthropic-compatible endpoint. Use it anywhere as
        <code className="mx-1 rounded bg-zinc-800 px-1">custom:alias</code>.
      </p>

      <section className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <h2 className="mb-3 text-sm font-semibold">Add custom model</h2>
          <div className="grid gap-2 text-sm">
            <input
              placeholder="alias (e.g. my-vllm)"
              value={form.alias}
              onChange={(event) => setForm({ ...form, alias: event.target.value })}
              className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
            />
            <select
              value={form.format}
              onChange={(event) => setForm({ ...form, format: event.target.value })}
              className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
            >
              <option value="openai">OpenAI-compatible (/chat/completions)</option>
              <option value="anthropic">Anthropic-compatible (/v1/messages)</option>
            </select>
            <input
              placeholder="base_url (http://localhost:8001/v1)"
              value={form.base_url}
              onChange={(event) => setForm({ ...form, base_url: event.target.value })}
              className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
            />
            <input
              placeholder="model id on the provider"
              value={form.model}
              onChange={(event) => setForm({ ...form, model: event.target.value })}
              className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
            />
            <input
              placeholder="api key (optional)"
              type="password"
              value={form.api_key}
              onChange={(event) => setForm({ ...form, api_key: event.target.value })}
              className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
            />
            <label className="flex items-center gap-2 text-xs text-zinc-400">
              <input
                type="checkbox"
                checked={form.supports_tools}
                onChange={(event) => setForm({ ...form, supports_tools: event.target.checked })}
              />
              supports tool calling
            </label>
            <button onClick={submit} className="rounded-lg bg-emerald-600 px-3 py-2 font-medium hover:bg-emerald-500">
              Save model
            </button>
            {result && <p className="text-xs text-zinc-400">{result}</p>}
          </div>
        </div>

        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <h2 className="mb-3 text-sm font-semibold">Available</h2>
          <div className="space-y-2">
            {data?.models.map((model) => (
              <div key={model.id} className="flex items-center gap-2 rounded-lg border border-zinc-800 p-2 text-sm">
                <span className="font-mono">{model.id}</span>
                {model.custom && (
                  <span className="rounded bg-violet-800 px-1.5 text-[10px] uppercase">{model.format}</span>
                )}
                <div className="ml-auto flex gap-2">
                  <button
                    onClick={async () => setResult(JSON.stringify(await testModel(model.id)))}
                    className="rounded border border-zinc-700 px-2 py-0.5 text-xs"
                  >
                    Test
                  </button>
                  {model.custom && (
                    <button
                      onClick={() => deleteCustomModel(model.id.replace("custom:", "")).then(refresh)}
                      className="rounded bg-red-800 px-2 py-0.5 text-xs"
                    >
                      Remove
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 text-xs text-zinc-500">
            Defaults: {Object.entries(data?.defaults ?? {}).map(([key, value]) => `${key}=${value}`).join("  ·  ")}
          </div>
        </div>
      </section>
    </main>
  )
}
