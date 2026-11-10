import assert from 'node:assert/strict'
import test from 'node:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const server = await createServer({
  root,
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'error',
  ssr: { external: ['react', 'react-dom'] },
})
const { DebugWorkbench } = await server.ssrLoadModule('/src/pages/DebugPage.tsx')

const catalog = {
  data: [{ id: 'codex/gpt-6-astra', endpoint: '/v1/responses', owned_by: 'codex' }],
  log_request_body: true,
  errors: [
    { provider: 'xai', message: 'refresh token may already have been consumed', type: 'credential_error' },
    { provider: 'deepseek-a', message: 'Models endpoint returned HTTP 404', type: 'model_discovery_error' },
  ],
}

function render(overrides = {}) {
  return renderToStaticMarkup(DebugWorkbench({
    catalog,
    loading: false,
    discoveryError: '',
    modelId: catalog.data[0].id,
    prompt: '',
    pending: false,
    result: null,
    onReload: () => {},
    onModelChange: () => {},
    onPromptChange: () => {},
    onSubmit: (event) => event.preventDefault(),
    ...overrides,
  }))
}

test('debug page uses the dashboard form shell and groups refresh with the model field', () => {
  const html = render()
  assert.match(html, /<h2>Model Debug<\/h2>/)
  assert.match(html, /log_request_body/)
  assert.match(html, /currently <strong>enabled<\/strong>/)
  const form = html.slice(html.indexOf('<form'), html.indexOf('</form>'))
  assert.match(form, /Refresh models/)
  assert.match(form, /id="debug-model"/)
  assert.match(form, /id="debug-prompt"/)
  assert.match(form, /Run request/)
  assert.match(form, /POST \/v1\/responses/)
  assert.doesNotMatch(html, /class="debug-heading"/)
})

test('discovery warnings stay in a collapsed disclosure instead of an open banner', () => {
  const html = render()
  assert.match(html, /aria-label="Model discovery warnings"/)
  assert.match(html, /<details class="debug-callout debug-callout-warning">/)
  assert.doesNotMatch(html, /<details class="debug-callout debug-callout-warning" open/)
  assert.match(html, /2/)
  assert.match(html, /providers reported discovery problems/)
  assert.match(html, /Models that were listed remain available/)
  assert.match(html, /deepseek-a/)
  assert.match(html, /Models endpoint returned HTTP 404/)
  assert.match(html, /credential_error/)
})

test('a failed discovery is an alert and an empty catalog explains how to recover', () => {
  const failed = render({ catalog: null, discoveryError: 'Model discovery failed: HTTP 503' })
  assert.match(failed, /role="alert"/)
  assert.match(failed, /Model discovery failed: HTTP 503/)
  assert.match(failed, /Refresh models/)

  const empty = render({ catalog: { data: [], errors: [], log_request_body: false } })
  assert.match(empty, /role="status"/)
  assert.match(empty, /No text-capable models discovered/)
  assert.match(empty, /currently <strong>disabled<\/strong>/)
})

test('a finished request keeps the answer, usage, and raw payloads', () => {
  const html = render({
    prompt: 'Hello',
    result: {
      model: 'codex/gpt-6-astra',
      endpoint: '/v1/responses',
      httpStatus: 200,
      elapsedMs: 42,
      ok: true,
      answer: 'hello back',
      usage: { input_tokens: 3, output_tokens: 2 },
      error: null,
      request: { model: 'codex/gpt-6-astra' },
      raw: { status: 'completed' },
    },
  })
  assert.match(html, /aria-label="Debug result"/)
  assert.match(html, /Request completed/)
  assert.match(html, /hello back/)
  assert.match(html, /Raw request JSON/)
  assert.match(html, /Raw response JSON/)
  assert.match(html, /input_tokens/)
})

test.after(async () => {
  await server.close()
})
