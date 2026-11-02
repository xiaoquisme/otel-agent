export type DebugEndpoint = '/v1/chat/completions' | '/v1/messages' | '/v1/responses'

export interface DebugModel {
  id: string
  owned_by: string
  endpoint: DebugEndpoint
}

export interface DebugCatalog {
  data: DebugModel[]
  errors: { provider: string; message: string; type: string }[]
  log_request_body: boolean
}

export interface DebugResult {
  model: string
  endpoint: DebugEndpoint
  httpStatus: number | null
  elapsedMs: number
  ok: boolean
  answer: string
  usage: unknown
  error: unknown
  request: unknown
  raw: unknown
}

export async function discoverDebugModels(signal?: AbortSignal, fetcher: typeof fetch = fetch): Promise<DebugCatalog> {
  const response = await fetcher('/api/debug/models', { signal })
  if (!response.ok) throw new Error(`Model discovery failed: HTTP ${response.status}`)
  return response.json() as Promise<DebugCatalog>
}

function object(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : {}
}

function textBlocks(value: unknown, type: string): string {
  if (typeof value === 'string') return value
  if (!Array.isArray(value)) return ''
  return value.flatMap((part) => {
    const block = object(part)
    return block.type === type && typeof block.text === 'string' ? [block.text] : []
  }).join('\n')
}

function answerText(body: Record<string, unknown>, endpoint: DebugEndpoint): string {
  if (endpoint === '/v1/messages') return textBlocks(body.content, 'text')
  if (endpoint === '/v1/responses') {
    if (!Array.isArray(body.output)) return ''
    return body.output.filter((item) => object(item).type === 'message')
      .map((item) => textBlocks(object(item).content, 'output_text')).filter(Boolean).join('\n')
  }
  const first = Array.isArray(body.choices) ? object(body.choices[0]) : {}
  const message = object(first.message)
  return textBlocks(message.content, 'text') || (typeof message.refusal === 'string' ? message.refusal : '')
}

export async function runDebug(model: DebugModel, prompt: string, fetcher: typeof fetch = fetch): Promise<DebugResult> {
  // Only server-selected native gateway endpoints; never an arbitrary URL/JSON editor.
  if (!['/v1/chat/completions', '/v1/messages', '/v1/responses'].includes(model.endpoint)) {
    throw new Error('Unsupported debug endpoint')
  }
  const body = model.endpoint === '/v1/responses'
    ? { model: model.id, stream: false, input: [
      { role: 'user', content: [{ type: 'input_text', text: prompt }] },
    ] }
    : { model: model.id, stream: false,
      ...(model.endpoint === '/v1/messages' ? { max_tokens: 1024 } : {}),
      messages: [{ role: 'user', content: prompt }] }
  const started = performance.now()
  const result: DebugResult = {
    model: model.id, endpoint: model.endpoint, httpStatus: null, elapsedMs: 0,
    ok: false, answer: '', usage: null, error: null, request: body, raw: null,
  }
  try {
    const response = await fetcher(model.endpoint, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    })
    result.httpStatus = response.status
    const raw = await response.text()
    let isJson = true
    try { result.raw = JSON.parse(raw) } catch { result.raw = raw; isJson = false }
    const payload = object(result.raw)
    const unfinished = model.endpoint === '/v1/responses'
      && typeof payload.status === 'string' && payload.status !== 'completed'
    result.ok = response.ok && isJson && !payload.error && !unfinished
    result.answer = answerText(payload, model.endpoint)
    result.usage = payload.usage ?? null
    result.error = payload.error || (unfinished
      ? { type: 'response_not_completed', status: payload.status, details: payload.incomplete_details ?? null }
      : !result.ok ? { type: 'gateway_error', message: `HTTP ${response.status}${isJson ? '' : ': non-JSON response'}` } : null)
  } catch (error) {
    result.error = { type: 'network_error', message: error instanceof Error ? error.message : String(error) }
  }
  result.elapsedMs = performance.now() - started
  return result
}
