import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { discoverDebugModels, runDebug } from '../api/debug'
import type { DebugCatalog, DebugResult } from '../api/debug'
import { Badge, Button, Card, Select } from '../components/ui'
import './DebugPage.css'

const pretty = (value: unknown) => typeof value === 'string' ? value : JSON.stringify(value, null, 2)

export interface DebugWorkbenchProps {
  catalog: DebugCatalog | null
  loading: boolean
  discoveryError: string
  modelId: string
  prompt: string
  pending: boolean
  result: DebugResult | null
  onReload: () => void
  onModelChange: (modelId: string) => void
  onPromptChange: (prompt: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

function statusColor(status: number | null): string {
  if (status == null) return 'var(--color-text-secondary)'
  if (status >= 200 && status < 300) return 'var(--color-accent-green)'
  if (status >= 400) return 'var(--color-accent-red)'
  return 'var(--color-text-primary)'
}

export function DebugWorkbench({
  catalog,
  loading,
  discoveryError,
  modelId,
  prompt,
  pending,
  result,
  onReload,
  onModelChange,
  onPromptChange,
  onSubmit,
}: DebugWorkbenchProps) {
  const selected = catalog?.data.find((model) => model.id === modelId)
  const canRun = !pending && !loading && !!selected && prompt.trim().length > 0
  const warningCount = catalog?.errors.length ?? 0

  return (
    <main className="debug-page">
      <header className="debug-page-header">
        <h2>Model Debug</h2>
        <p className="debug-lede">
          Single-turn text request through the real gateway. Running may consume provider quota or incur charges.
        </p>
      </header>

      <div className="debug-callout debug-callout-info">
        <p>
          Credentials stay on the server. Prompt logging follows <code>log_request_body</code>
          {catalog ? <> (currently <strong>{catalog.log_request_body ? 'enabled' : 'disabled'}</strong>)</> : ''}.
          {' '}Responses are recorded in request telemetry. Do not enter secrets.
        </p>
      </div>

      {discoveryError && (
        <p role="alert" className="debug-callout debug-callout-error">
          {discoveryError} — use Refresh models to retry.
        </p>
      )}

      {warningCount > 0 && (
        <section aria-label="Model discovery warnings">
          <details className="debug-callout debug-callout-warning">
            <summary>
              <Badge variant="warning" size="sm">{warningCount}</Badge>
              <span>
                {warningCount === 1 ? 'provider reported a discovery problem' : 'providers reported discovery problems'}.
                {' '}Models that were listed remain available.
              </span>
            </summary>
            <ul className="debug-warning-list">
              {catalog?.errors.map((error, index) => (
                <li key={`${error.provider}-${error.type}-${index}`}>
                  <span className="debug-warning-provider">{error.provider}</span>
                  <span className="debug-warning-message">{error.message}</span>
                  <span className="debug-warning-type">{error.type}</span>
                </li>
              ))}
            </ul>
          </details>
        </section>
      )}

      {!loading && catalog?.data.length === 0 && (
        <p role="status" className="debug-callout debug-callout-status">
          No text-capable models discovered. Check provider configuration or discovery warnings, then refresh. Models with unknown capabilities are included.
        </p>
      )}

      <Card className="debug-card" padding="md">
        <form onSubmit={onSubmit} aria-busy={pending}>
          <div className="debug-field">
            <label className="debug-label" htmlFor="debug-model">Model</label>
            <div className="debug-model-control">
              <Select
                id="debug-model"
                fullWidth
                size="md"
                value={modelId}
                onChange={(event) => onModelChange(event.target.value)}
                disabled={loading || pending || !catalog?.data.length}
                aria-describedby="debug-protocol"
              >
                {!catalog?.data.length && <option value="">{loading ? 'Loading models…' : 'No models available'}</option>}
                {catalog?.data.map((model) => <option key={model.id} value={model.id}>{model.id}</option>)}
              </Select>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={onReload}
                disabled={loading || pending}
                loading={loading}
              >
                {loading ? 'Discovering…' : 'Refresh models'}
              </Button>
            </div>
            <p id="debug-protocol" className="debug-help">
              Protocol: <code>{selected ? `POST ${selected.endpoint}` : '—'}</code>. Text input only; no conversation history, tools or media.
            </p>
          </div>

          <div className="debug-field">
            <label className="debug-label" htmlFor="debug-prompt">Prompt</label>
            <textarea
              id="debug-prompt"
              rows={6}
              value={prompt}
              onChange={(event) => onPromptChange(event.target.value)}
              placeholder="Enter a text prompt…"
              disabled={pending}
              required
            />
          </div>

          <div className="debug-actions">
            <Button type="submit" variant="primary" size="sm" disabled={!canRun} loading={pending}>
              {pending ? 'Running…' : 'Run request'}
            </Button>
            <span role="status" className="debug-help">
              {pending
                ? 'Waiting for gateway response. Do not resubmit.'
                : 'Anthropic output limit: 1,024 tokens. Other protocols use upstream defaults.'}
            </span>
          </div>
        </form>
      </Card>

      {result && (
        <Card className="debug-card" padding="md">
          <section className="debug-result" aria-label="Debug result" aria-live="polite">
            <div className="debug-result-heading">
              <h3>{result.ok ? 'Request completed' : 'Request failed / not completed'}</h3>
              <Badge variant={result.ok ? 'success' : 'error'} size="sm">
                {result.ok ? 'completed' : 'not completed'}
              </Badge>
            </div>
            <dl className="debug-metrics">
              <div><dt>Model</dt><dd>{result.model}</dd></div>
              <div><dt>Protocol</dt><dd>POST {result.endpoint}</dd></div>
              <div>
                <dt>HTTP status</dt>
                <dd style={{ color: statusColor(result.httpStatus) }}>{result.httpStatus ?? 'No HTTP response'}</dd>
              </div>
              <div><dt>Elapsed</dt><dd>{result.elapsedMs.toFixed(0)} ms</dd></div>
            </dl>
            {result.error != null && (
              <div role="alert" className="debug-callout debug-callout-error">
                <h4>Error</h4>
                <pre>{pretty(result.error)}</pre>
              </div>
            )}
            <h4>Answer</h4>
            <pre className="debug-answer">{result.answer || 'No text returned. See error / raw response for details.'}</pre>
            <h4>Usage (provider reported)</h4>
            {result.usage != null
              ? <pre>{pretty(result.usage)}</pre>
              : <p className="debug-help">Usage not reported. No token estimate is made.</p>}
            <details className="debug-disclosure">
              <summary>Raw request JSON</summary>
              <pre>{pretty(result.request)}</pre>
            </details>
            <details className="debug-disclosure">
              <summary>Raw response {typeof result.raw === 'string' ? '(non-JSON)' : 'JSON'}</summary>
              <pre>{result.raw === null ? 'No response body received.' : pretty(result.raw)}</pre>
            </details>
          </section>
        </Card>
      )}
    </main>
  )
}

export default function DebugPage() {
  const [catalog, setCatalog] = useState<DebugCatalog | null>(null)
  const [loading, setLoading] = useState(true)
  const [discoveryError, setDiscoveryError] = useState('')
  const [reload, setReload] = useState(0)
  const [modelId, setModelId] = useState('')
  const [prompt, setPrompt] = useState('')
  const [pending, setPending] = useState(false)
  const running = useRef(false)
  const [result, setResult] = useState<DebugResult | null>(null)
  const selected = catalog?.data.find((model) => model.id === modelId)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setDiscoveryError('')
    discoverDebugModels(controller.signal).then((data) => {
      if (controller.signal.aborted) return
      setCatalog(data)
      setModelId((previous) => data.data.some((model) => model.id === previous) ? previous : data.data[0]?.id ?? '')
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) {
        setCatalog(null)
        setDiscoveryError(error instanceof Error ? error.message : String(error))
      }
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })
    return () => controller.abort()
  }, [reload])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (running.current || !selected || !prompt.trim() || loading) return
    running.current = true
    setPending(true)
    setResult(null)
    try {
      setResult(await runDebug(selected, prompt))
    } finally {
      running.current = false
      setPending(false)
    }
  }

  return (
    <DebugWorkbench
      catalog={catalog}
      loading={loading}
      discoveryError={discoveryError}
      modelId={modelId}
      prompt={prompt}
      pending={pending}
      result={result}
      onReload={() => setReload((value) => value + 1)}
      onModelChange={setModelId}
      onPromptChange={setPrompt}
      onSubmit={submit}
    />
  )
}
