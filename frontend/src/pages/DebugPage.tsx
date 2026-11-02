import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { discoverDebugModels, runDebug } from '../api/debug'
import type { DebugCatalog, DebugResult } from '../api/debug'
import './DebugPage.css'

const pretty = (value: unknown) => typeof value === 'string' ? value : JSON.stringify(value, null, 2)

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
    <main className="debug-page">
      <div className="debug-heading">
        <h2>Model Debug</h2>
        <button type="button" onClick={() => setReload((value) => value + 1)} disabled={loading || pending}>
          {loading ? 'Discovering…' : 'Refresh models'}
        </button>
      </div>
      <p className="debug-muted">Single-turn text request through the real gateway. Running may consume provider quota or incur charges.</p>
      <p className="debug-notice">
        Credentials stay on the server. Prompt logging follows <code>log_request_body</code>
        {catalog ? <> (currently <strong>{catalog.log_request_body ? 'enabled' : 'disabled'}</strong>)</> : ''}.
        {' '}Responses are recorded in request telemetry. Do not enter secrets.
      </p>
      {discoveryError && <p role="alert" className="debug-error">{discoveryError} — use Refresh models to retry.</p>}
      {catalog && catalog.errors.length > 0 && (
        <section className="debug-notice" aria-label="Model discovery warnings">
          <strong>Some providers reported discovery problems. Models that were listed remain available.</strong>
          <ul>{catalog.errors.map((error) => <li key={error.provider}>{error.provider}: {error.message} ({error.type})</li>)}</ul>
        </section>
      )}
      {!loading && catalog?.data.length === 0 && <p role="status">No text-capable models discovered. Check provider configuration or discovery warnings, then refresh. Models with unknown capabilities are included.</p>}
      <form onSubmit={submit} aria-busy={pending}>
        <label htmlFor="debug-model">Model</label>
        <select id="debug-model" value={modelId} onChange={(event) => setModelId(event.target.value)} disabled={loading || pending || !catalog?.data.length}>
          {!catalog?.data.length && <option value="">{loading ? 'Loading models…' : 'No models available'}</option>}
          {catalog?.data.map((model) => <option key={model.id} value={model.id}>{model.id}</option>)}
        </select>
        <p className="debug-muted">Protocol: <code>{selected ? `POST ${selected.endpoint}` : '—'}</code>. Text input only; no conversation history, tools or media.</p>
        <label htmlFor="debug-prompt">Prompt</label>
        <textarea id="debug-prompt" rows={6} value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Enter a text prompt…" disabled={pending} required />
        <div className="debug-actions">
          <button type="submit" disabled={pending || loading || !selected || !prompt.trim()}>{pending ? 'Running…' : 'Run request'}</button>
          <span role="status" className="debug-muted">{pending ? 'Waiting for gateway response. Do not resubmit.' : 'Anthropic output limit: 1,024 tokens. Other protocols use upstream defaults.'}</span>
        </div>
      </form>
      {result && (
        <section className="debug-result" aria-label="Debug result" aria-live="polite">
          <h3>{result.ok ? 'Request completed' : 'Request failed / not completed'}</h3>
          <dl className="debug-metrics">
            <div><dt>Model</dt><dd>{result.model}</dd></div>
            <div><dt>Protocol</dt><dd>POST {result.endpoint}</dd></div>
            <div><dt>HTTP status</dt><dd>{result.httpStatus ?? 'No HTTP response'}</dd></div>
            <div><dt>Elapsed</dt><dd>{result.elapsedMs.toFixed(0)} ms</dd></div>
          </dl>
          {result.error != null && <div role="alert" className="debug-error"><h4>Error</h4><pre>{pretty(result.error)}</pre></div>}
          <h4>Answer</h4>
          <pre className="debug-answer">{result.answer || 'No text returned. See error / raw response for details.'}</pre>
          <h4>Usage (provider reported)</h4>
          {result.usage != null ? <pre>{pretty(result.usage)}</pre> : <p className="debug-muted">Usage not reported. No token estimate is made.</p>}
          <details>
            <summary>Raw request JSON</summary>
            <pre>{pretty(result.request)}</pre>
          </details>
          <details>
            <summary>Raw response {typeof result.raw === 'string' ? '(non-JSON)' : 'JSON'}</summary>
            <pre>{result.raw === null ? 'No response body received.' : pretty(result.raw)}</pre>
          </details>
        </section>
      )}
    </main>
  )
}
