import test from 'node:test'
import assert from 'node:assert/strict'
import { discoverDebugModels, runDebug } from '../src/api/debug.ts'

const models = [
  { id: 'chat/claude-name', endpoint: '/v1/chat/completions', owned_by: 'chat' },
  { id: 'anthropic/gpt-name', endpoint: '/v1/messages', owned_by: 'anthropic' },
  { id: 'responses/other', endpoint: '/v1/responses', owned_by: 'responses' },
]

for (const model of models) {
  test(`${model.endpoint}: sends only fixed text payload without credentials`, async () => {
    let calls = 0
    const mockFetch = async (url, init) => {
      calls++
      assert.equal(url, model.endpoint)
      assert.equal(init.method, 'POST')
      assert.deepEqual(init.headers, { 'Content-Type': 'application/json' })
      const body = JSON.parse(init.body)
      assert.equal(body.model, model.id)
      assert.equal(body.stream, false)
      if (url === '/v1/responses') {
        assert.deepEqual(body.input, [{ role: 'user', content: [{ type: 'input_text', text: 'Hello' }] }])
        assert.equal(body.instructions, '')
        assert.equal(body.messages, undefined)
      } else {
        assert.deepEqual(body.messages, [{ role: 'user', content: 'Hello' }])
        assert.equal(body.max_tokens, url === '/v1/messages' ? 1024 : undefined)
        assert.equal(body.input, undefined)
      }
      const native = url === '/v1/chat/completions'
        ? { choices: [{ message: { content: 'answer' } }] }
        : url === '/v1/messages'
          ? { content: [{ type: 'text', text: 'answer' }] }
          : { status: 'completed', output: [{ type: 'message', content: [{ type: 'output_text', text: 'answer' }] }] }
      return Response.json({ ...native, usage: { input_tokens: 3, output_tokens: 2 } })
    }
    const result = await runDebug(model, 'Hello', mockFetch)
    assert.equal(calls, 1)
    assert.equal(result.ok, true)
    assert.equal(result.httpStatus, 200)
    assert.equal(result.answer, 'answer')
    assert.equal(result.usage.input_tokens, 3)
    assert.ok(result.elapsedMs >= 0)
    assert.equal(result.error, null)
  })

  test(`${model.endpoint}: preserves upstream HTTP errors and raw JSON`, async () => {
    const raw = { error: { type: 'invalid_model', message: 'Unknown model' } }
    const result = await runDebug(model, 'Hello', async () => Response.json(raw, { status: 404 }))
    assert.equal(result.ok, false)
    assert.equal(result.httpStatus, 404)
    assert.deepEqual(result.raw, raw)
    assert.deepEqual(result.error, raw.error)
    assert.equal(result.answer, '')
  })
}

test('an error inside a 200 response is not labeled successful', async () => {
  const result = await runDebug(models[0], 'Hello', async () => Response.json({ error: { message: 'rejected' } }))
  assert.equal(result.httpStatus, 200)
  assert.equal(result.ok, false)
})

for (const status of ['failed', 'incomplete', 'cancelled']) {
  test(`Responses ${status} is not a complete successful answer`, async () => {
    const result = await runDebug(models[2], 'Hello', async () => Response.json({ status, incomplete_details: { reason: 'max_output_tokens' } }))
    assert.equal(result.ok, false)
    assert.ok(result.error)
  })
}

test('non-JSON errors keep their body and status', async () => {
  const result = await runDebug(models[0], 'Hello', async () => new Response('bad gateway', { status: 502 }))
  assert.equal(result.httpStatus, 502)
  assert.equal(result.ok, false)
  assert.equal(result.raw, 'bad gateway')
})

test('network failures are distinct from HTTP failures', async () => {
  const result = await runDebug(models[0], 'Hello', async () => { throw new TypeError('offline') })
  assert.equal(result.httpStatus, null)
  assert.equal(result.error.type, 'network_error')
  assert.equal(result.ok, false)
})

test('unknown execution endpoints cannot become arbitrary URL calls', async () => {
  let called = false
  await assert.rejects(runDebug({ ...models[0], endpoint: 'https://evil.test' }, 'Hello', async () => { called = true }), /Unsupported/)
  assert.equal(called, false)
})

test('discovery keeps partial failures alongside available models and logging setting', async () => {
  const data = { data: models, errors: [{ provider: 'broken', message: 'unavailable' }], log_request_body: false }
  const result = await discoverDebugModels(undefined, async (url) => {
    assert.equal(url, '/api/debug/models')
    return Response.json(data)
  })
  assert.deepEqual(result, data)
})

test('failed discovery reports HTTP status, not an empty successful list', async () => {
  await assert.rejects(discoverDebugModels(undefined, async () => Response.json({ error: 'unavailable' }, { status: 503 })), /503/)
})
