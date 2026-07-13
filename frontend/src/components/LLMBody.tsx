import { useState } from 'react'

interface LLMBodyProps {
  body: string | null
  renderedHtml: string | null
}

function highlightJson(obj: unknown, indent: number = 0): string {
  const pad = '  '.repeat(indent)

  if (obj === null) return `${pad}<span class="json-null">null</span>`
  if (typeof obj === 'boolean') return `${pad}<span class="json-boolean">${obj}</span>`
  if (typeof obj === 'number') return `${pad}<span class="json-number">${obj}</span>`
  if (typeof obj === 'string') {
    const escaped = obj.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
    return `${pad}<span class="json-string">"${escaped}"</span>`
  }

  if (Array.isArray(obj)) {
    if (obj.length === 0) return `${pad}[]`
    const items = obj.map((v) => highlightJson(v, indent + 1))
    return `${pad}[\n${items.join(',\n')}\n${pad}]`
  }

  if (typeof obj === 'object') {
    const keys = Object.keys(obj as Record<string, unknown>)
    if (keys.length === 0) return `${pad}{}`
    const entries = keys.map((k) => {
      const escaped = k.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
      return `${pad}  <span class="json-key">"${escaped}"</span>: ${highlightJson((obj as Record<string, unknown>)[k], indent + 1).trim()}`
    })
    return `${pad}{\n${entries.join(',\n')}\n${pad}}`
  }

  return pad + String(obj)
}

export default function LLMBody({ body, renderedHtml }: LLMBodyProps) {
  const [view, setView] = useState<'llm' | 'raw'>('llm')

  if (!body) {
    return <div className="text-[#8b949e] italic">(empty)</div>
  }

  let parsed: unknown = null
  let isValidJson = false
  try {
    parsed = JSON.parse(body)
    isValidJson = true
  } catch {
    // Not JSON
  }

  // Non-JSON body
  if (!isValidJson) {
    return (
      <div className="body-raw">
        <div className="text-[#8b949e] text-xs mt-1">Content is not valid JSON</div>
        <pre className="bg-[#0d1117] p-3 rounded-md overflow-x-auto text-[13px] leading-relaxed whitespace-pre-wrap break-all max-h-[600px] overflow-y-auto">
          {body}
        </pre>
      </div>
    )
  }

  const hasRendered = renderedHtml && renderedHtml.trim().length > 0
  const rawHtml = `<pre>${highlightJson(parsed, 0)}</pre>`

  if (hasRendered) {
    return (
      <div className="body-viewer relative">
        <div className="body-toggle-bar flex gap-1 mb-2">
          <button
            className={`body-toggle-btn px-2 py-0.5 rounded text-xs border border-[#30363d] cursor-pointer ${
              view === 'llm'
                ? 'bg-[#30363d] text-[#e1e4e8]'
                : 'bg-[#21262d] text-[#8b949e] hover:bg-[#30363d]'
            }`}
            onClick={() => setView('llm')}
          >
            Formatted
          </button>
          <button
            className={`body-toggle-btn px-2 py-0.5 rounded text-xs border border-[#30363d] cursor-pointer ${
              view === 'raw'
                ? 'bg-[#30363d] text-[#e1e4e8]'
                : 'bg-[#21262d] text-[#8b949e] hover:bg-[#30363d]'
            }`}
            onClick={() => setView('raw')}
          >
            Raw
          </button>
        </div>
        {view === 'llm' && (
          <div className="body-llm-view" dangerouslySetInnerHTML={{ __html: renderedHtml }} />
        )}
        {view === 'raw' && (
          <div className="body-raw-view" dangerouslySetInnerHTML={{ __html: rawHtml }} />
        )}
      </div>
    )
  }

  // Valid JSON but no LLM rendering
  return (
    <div className="body-raw">
      <pre
        className="bg-[#0d1117] p-3 rounded-md overflow-x-auto text-[13px] leading-relaxed whitespace-pre-wrap break-all max-h-[600px] overflow-y-auto"
        dangerouslySetInnerHTML={{ __html: highlightJson(parsed, 0) }}
      />
    </div>
  )
}
