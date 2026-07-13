import { useState, useEffect, useCallback } from 'react'
import type { RequestDetail } from '../api/types'
import { fetchRequestDetail } from '../api/client'
import MessageDisplay from './MessageDisplay'

interface DetailPanelProps {
  requestId: number | null
  onClose: () => void
}

function formatHeaders(
  headers: Record<string, string> | string | null
): string {
  if (!headers) return '(none)'
  if (typeof headers === 'string') {
    try {
      const parsed = JSON.parse(headers) as Record<string, string>
      return Object.entries(parsed)
        .map(([k, v]) => `${k}: ${v}`)
        .join('\n')
    } catch {
      return headers
    }
  }
  return Object.entries(headers)
    .map(([k, v]) => `${k}: ${v}`)
    .join('\n')
}

function copyCurl(r: RequestDetail): void {
  let curl = `curl -X ${r.method} '${r.url}'`
  const headers =
    typeof r.request_headers === 'string'
      ? (JSON.parse(r.request_headers) as Record<string, string>)
      : r.request_headers
  if (headers) {
    for (const [k, v] of Object.entries(headers)) {
      if (k.toLowerCase() !== 'host') {
        curl += ` \\\n  -H '${k}: ${v}'`
      }
    }
  }
  if (r.request_body) {
    curl += ` \\\n  -d '${r.request_body}'`
  }
  navigator.clipboard.writeText(curl)
}

export default function DetailPanel({ requestId, onClose }: DetailPanelProps) {
  const [detail, setDetail] = useState<RequestDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [view, setView] = useState<'formatted' | 'raw'>('formatted')

  useEffect(() => {
    if (requestId === null) {
      setDetail(null)
      return
    }
    setLoading(true)
    setView('formatted')
    fetchRequestDetail(requestId)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false))
  }, [requestId])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    },
    [onClose]
  )

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const isOpen = requestId !== null

  return (
    <div
      className={`fixed top-0 right-0 bottom-0 w-1/2 bg-[#161b22] border-l border-[#30363d] overflow-y-auto z-10 transition-transform duration-200 ${
        isOpen ? 'translate-x-0' : 'translate-x-full'
      }`}
    >
      <div className="flex justify-between items-center px-6 py-4 border-b border-[#30363d]">
        <h2 className="text-base font-semibold">Request Details</h2>
        <button
          className="bg-transparent border-none text-[#8b949e] cursor-pointer text-xl hover:text-[#e1e4e8]"
          onClick={onClose}
        >
          &times;
        </button>
      </div>
      <div className="px-6 py-4">
        {loading && (
          <div className="text-[#8b949e] text-sm py-8 text-center">Loading...</div>
        )}
        {!loading && !detail && (
          <div className="text-[#8b949e] text-sm py-8 text-center">No data</div>
        )}
        {!loading && detail && (
          <>
            {/* General */}
            <div className="mb-5">
              <h3 className="text-xs text-[#8b949e] uppercase mb-2">General</h3>
              <pre className="bg-[#0d1117] p-3 rounded-md text-[13px] leading-relaxed whitespace-pre-wrap break-all">
                {`${detail.method} ${detail.url}\nStatus: ${detail.response_status} | Latency: ${detail.latency_ms?.toFixed(0) ?? 0}ms`}
              </pre>
              <button
                className="mt-2 bg-[#21262d] border border-[#30363d] text-[#8b949e] px-2.5 py-1 rounded text-xs cursor-pointer hover:bg-[#30363d] hover:text-[#e1e4e8]"
                onClick={() => copyCurl(detail)}
              >
                Copy as curl
              </button>
            </div>

            {/* View toggle */}
            <div className="flex gap-1 mb-4">
              <button
                className={`px-2 py-0.5 rounded text-xs border border-[#30363d] cursor-pointer ${
                  view === 'formatted'
                    ? 'bg-[#30363d] text-[#e1e4e8]'
                    : 'bg-[#21262d] text-[#8b949e] hover:bg-[#30363d]'
                }`}
                onClick={() => setView('formatted')}
              >
                Formatted
              </button>
              <button
                className={`px-2 py-0.5 rounded text-xs border border-[#30363d] cursor-pointer ${
                  view === 'raw'
                    ? 'bg-[#30363d] text-[#e1e4e8]'
                    : 'bg-[#21262d] text-[#8b949e] hover:bg-[#30363d]'
                }`}
                onClick={() => setView('raw')}
              >
                Raw
              </button>
            </div>

            {view === 'formatted' ? (
              <>
                {/* Request Messages */}
                <div className="mb-5 border-l-[3px] border-[#58a6ff] bg-[rgba(88,166,255,0.05)] pl-3">
                  <h3 className="text-xs text-[#8b949e] uppercase mb-2">
                    Request
                  </h3>
                  <MessageDisplay
                    messages={detail.messages?.filter((_, i) => i < (detail.messages?.length ?? 0) - (detail.metadata?.model ? 1 : 0)) ?? []}
                    metadata={null}
                  />
                </div>

                {/* Response Messages */}
                <div className="mb-5 border-l-[3px] border-[#3fb950] bg-[rgba(63,185,80,0.05)] pl-3">
                  <h3 className="text-xs text-[#8b949e] uppercase mb-2">
                    Response
                  </h3>
                  <MessageDisplay
                    messages={detail.metadata?.model ? detail.messages?.slice(-1) ?? [] : []}
                    metadata={detail.metadata}
                  />
                </div>
              </>
            ) : (
              <>
                {/* Raw Request */}
                <div className="mb-5 border-l-[3px] border-[#58a6ff] bg-[rgba(88,166,255,0.05)] pl-3">
                  <h3 className="text-xs text-[#8b949e] uppercase mb-2">
                    Request Headers
                  </h3>
                  <pre className="bg-[#0d1117] p-3 rounded-md text-[13px] leading-relaxed whitespace-pre-wrap break-all">
                    {formatHeaders(detail.request_headers)}
                  </pre>
                </div>
                <div className="mb-5 border-l-[3px] border-[#58a6ff] bg-[rgba(88,166,255,0.05)] pl-3">
                  <h3 className="text-xs text-[#8b949e] uppercase mb-2">
                    Request Body
                  </h3>
                  <pre className="bg-[#0d1117] p-3 rounded-md text-[13px] leading-relaxed whitespace-pre-wrap break-all max-h-[600px] overflow-y-auto">
                    {detail.request_body || '(empty)'}
                  </pre>
                </div>

                {/* Raw Response */}
                <div className="mb-5 border-l-[3px] border-[#3fb950] bg-[rgba(63,185,80,0.05)] pl-3">
                  <h3 className="text-xs text-[#8b949e] uppercase mb-2">
                    Response Headers
                  </h3>
                  <pre className="bg-[#0d1117] p-3 rounded-md text-[13px] leading-relaxed whitespace-pre-wrap break-all">
                    {formatHeaders(detail.response_headers)}
                  </pre>
                </div>
                <div className="mb-5 border-l-[3px] border-[#3fb950] bg-[rgba(63,185,80,0.05)] pl-3">
                  <h3 className="text-xs text-[#8b949e] uppercase mb-2">
                    Response Body
                  </h3>
                  <pre className="bg-[#0d1117] p-3 rounded-md text-[13px] leading-relaxed whitespace-pre-wrap break-all max-h-[600px] overflow-y-auto">
                    {detail.response_body || '(empty)'}
                  </pre>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
