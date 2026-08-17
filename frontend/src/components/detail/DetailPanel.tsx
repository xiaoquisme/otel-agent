import { useState, useEffect, useCallback } from 'react'
import { fetchRequestDetail } from '../../api/client'
import type { RequestDetail } from '../../api/types'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import { ZapIcon, ChevronDownIcon, ChevronRightIcon, CloseIcon, Skeleton } from '../ui'

interface DetailPanelProps {
  requestId: number | null
  onClose: () => void
}

type DetailTab = 'conversation' | 'raw' | 'headers'

function formatHeaders(headers: Record<string, string> | string | null): string {
  if (!headers) return '(none)'
  if (typeof headers === 'string') {
    try {
      const parsed = JSON.parse(headers) as Record<string, string>
      return Object.entries(parsed).map(([k, v]) => `${k}: ${v}`).join('\n')
    } catch {
      return headers
    }
  }
  return Object.entries(headers).map(([k, v]) => `${k}: ${v}`).join('\n')
}

function MessageBubble({ role, content }: { role: string; content: string }) {
  const roleStyles: Record<string, { border: string; bg: string; text: string; label: string }> = {
    system: { border: 'var(--color-border-default)', bg: 'var(--color-bg-elevated)', text: 'var(--color-text-secondary)', label: 'SYSTEM' },
    user: { border: 'var(--color-accent-blue)', bg: 'var(--color-accent-blue-muted)', text: 'var(--color-accent-blue)', label: 'USER' },
    assistant: { border: 'var(--color-accent-green)', bg: 'var(--color-accent-green-muted)', text: 'var(--color-accent-green)', label: 'ASSISTANT' },
    tool: { border: 'var(--color-accent-yellow)', bg: 'var(--color-accent-yellow-muted)', text: 'var(--color-accent-yellow)', label: 'TOOL' },
  }
  const style = roleStyles[role] || roleStyles.assistant

  return (
    <div
      style={{
        borderRadius: 'var(--radius-md)',
        border: `1px solid ${style.border}`,
        background: style.bg,
        padding: 'var(--space-3)',
        marginBottom: 'var(--space-2)',
      }}
    >
      <div
        style={{
          fontSize: 'var(--text-xs)',
          fontFamily: 'var(--font-mono)',
          color: style.text,
          marginBottom: 'var(--space-2)',
          opacity: 0.8,
          letterSpacing: '0.05em',
        }}
      >
        {style.label}
      </div>
      <div style={{ fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-relaxed)' }}>
        {content ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
            {content}
          </ReactMarkdown>
        ) : (
          <span style={{ color: 'var(--color-text-muted)', fontStyle: 'italic' }}>(empty)</span>
        )}
      </div>
    </div>
  )
}

function ToolCallBlock({ name, arguments: args }: { name: string; arguments: string }) {
  const [expanded, setExpanded] = useState(false)

  let formatted = args
  try {
    formatted = JSON.stringify(JSON.parse(args), null, 2)
  } catch {
    // keep as-is
  }

  return (
    <div
      style={{
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--color-border-default)',
        background: 'var(--color-bg-base)',
        marginBottom: 'var(--space-2)',
        overflow: 'hidden',
      }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          padding: 'var(--space-2) var(--space-3)',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
          fontSize: 'var(--text-xs)',
          fontFamily: 'var(--font-mono)',
        }}
      >
        <span style={{ color: 'var(--color-accent-yellow)', display: 'inline-flex' }}><ZapIcon size={12} /></span>
        <span style={{ color: 'var(--color-text-primary)' }}>{name}</span>
        <span style={{ color: 'var(--color-text-secondary)', display: 'inline-flex', marginLeft: 'auto' }}>
          {expanded ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
        </span>
      </button>
      {expanded && (
        <pre
          style={{
            padding: '0 var(--space-3) var(--space-3)',
            borderTop: '1px solid var(--color-border-muted)',
            fontSize: 'var(--text-xs)',
            fontFamily: 'var(--font-mono)',
            color: 'var(--color-text-primary)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
            margin: 0,
          }}
        >
          {formatted}
        </pre>
      )}
    </div>
  )
}

export default function DetailPanel({ requestId, onClose }: DetailPanelProps) {
  const [detail, setDetail] = useState<RequestDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<DetailTab>('conversation')

  useEffect(() => {
    if (requestId === null) {
      setDetail(null)
      return
    }
    setLoading(true)
    setActiveTab('conversation')
    fetchRequestDetail(requestId)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false))
  }, [requestId])

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose()
  }, [onClose])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const isOpen = requestId !== null

  if (!isOpen) return null

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--color-bg-surface)',
        overflow: 'hidden',
      }}
    >
      {/* Panel header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: 'var(--space-2) var(--space-3)',
          borderBottom: '1px solid var(--color-border-default)',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <span
            style={{
              fontSize: 'var(--text-xs)',
              fontFamily: 'var(--font-mono)',
              color: 'var(--color-text-secondary)',
            }}
          >
            #{requestId}
          </span>
          {detail && (
            <span
              style={{
                padding: '1px 4px',
                borderRadius: '3px',
                background: detail.method === 'POST' ? 'var(--color-accent-purple-muted)' : 'var(--color-accent-green-muted)',
                color: detail.method === 'POST' ? 'var(--color-accent-purple)' : 'var(--color-accent-green)',
                fontSize: '9px',
                fontWeight: 'var(--font-semibold)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {detail.method}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--color-text-secondary)',
            cursor: 'pointer',
            fontSize: 'var(--text-sm)',
            padding: '2px 4px',
            display: 'inline-flex',
          }}
        >
          <CloseIcon size={14} />
        </button>
      </div>

      {/* Loading skeleton */}
      {loading && (
        <div style={{ padding: 'var(--space-3)', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <Skeleton width="100%" height="16px" />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-2)' }}>
            <Skeleton height="32px" />
            <Skeleton height="32px" />
            <Skeleton height="32px" />
          </div>
          <Skeleton width="100%" height="60px" />
          <Skeleton width="100%" height="60px" />
        </div>
      )}

      {/* Content */}
      {!loading && detail && (
        <>
          {/* URL bar */}
          <div
            style={{
              padding: 'var(--space-2) var(--space-3)',
              borderBottom: '1px solid var(--color-border-muted)',
              fontSize: 'var(--text-xs)',
              fontFamily: 'var(--font-mono)',
              color: 'var(--color-text-secondary)',
              wordBreak: 'break-all',
              flexShrink: 0,
            }}
          >
            {detail.url}
          </div>

          {/* Metadata grid */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: 'var(--space-2)',
              padding: 'var(--space-2) var(--space-3)',
              borderBottom: '1px solid var(--color-border-muted)',
              flexShrink: 0,
            }}
          >
            {[
              { label: 'Status', value: String(detail.response_status) },
              { label: 'Latency', value: `${detail.latency_ms?.toFixed(0) ?? 0}ms` },
              { label: 'Model', value: detail.model_name || detail.metadata?.model || '—' },
            ].map((item) => (
              <div key={item.label} style={{ fontSize: 'var(--text-xs)' }}>
                <div style={{ color: 'var(--color-text-muted)', marginBottom: '1px' }}>{item.label}</div>
                <div style={{ color: 'var(--color-text-primary)', fontFamily: 'var(--font-mono)' }}>{item.value}</div>
              </div>
            ))}
          </div>

          {/* Usage metrics */}
          {detail.metadata?.usage && (
            <div
              style={{
                display: 'flex',
                gap: 'var(--space-3)',
                padding: 'var(--space-2) var(--space-3)',
                borderBottom: '1px solid var(--color-border-muted)',
                fontSize: 'var(--text-xs)',
                fontFamily: 'var(--font-mono)',
                flexShrink: 0,
              }}
            >
              <span style={{ color: 'var(--color-text-muted)' }}>
                in: <span style={{ color: 'var(--color-text-primary)' }}>{detail.metadata.usage.input_tokens ?? '—'}</span>
              </span>
              <span style={{ color: 'var(--color-text-muted)' }}>
                out: <span style={{ color: 'var(--color-text-primary)' }}>{detail.metadata.usage.output_tokens ?? '—'}</span>
              </span>
              {detail.metadata.finish_reason && (
                <span style={{ color: 'var(--color-text-muted)' }}>
                  stop: <span style={{ color: 'var(--color-text-primary)' }}>{detail.metadata.finish_reason}</span>
                </span>
              )}
            </div>
          )}

          {/* Tabs */}
          <div
            style={{
              display: 'flex',
              borderBottom: '1px solid var(--color-border-default)',
              flexShrink: 0,
            }}
          >
            {(['conversation', 'raw', 'headers'] as DetailTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  padding: 'var(--space-2) var(--space-3)',
                  fontSize: 'var(--text-xs)',
                  fontFamily: 'var(--font-mono)',
                  background: activeTab === tab ? 'var(--color-bg-overlay)' : 'transparent',
                  border: 'none',
                  borderBottom: activeTab === tab ? '2px solid var(--color-accent-blue)' : '2px solid transparent',
                  color: activeTab === tab ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                  cursor: 'pointer',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div style={{ flex: 1, overflow: 'auto', padding: 'var(--space-3)' }}>
            {activeTab === 'conversation' && (
              <div>
                {/* Request messages */}
                {detail.messages?.filter(m => m.role !== 'assistant').map((msg, i) => (
                  <MessageBubble key={`req-${i}`} role={msg.role} content={msg.content || ''} />
                ))}

                {/* Tool calls from assistant */}
                {detail.messages?.filter(m => m.role === 'assistant').map((msg, i) => (
                  <div key={`resp-${i}`}>
                    {msg.content && <MessageBubble role="assistant" content={msg.content} />}
                    {msg.tool_calls?.map((tc, j) => (
                      <ToolCallBlock key={j} name={tc.name} arguments={tc.arguments} />
                    ))}
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'raw' && (
              <div>
                <div style={{ marginBottom: 'var(--space-3)' }}>
                  <div
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--color-text-muted)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      marginBottom: 'var(--space-2)',
                    }}
                  >
                    Request Body
                  </div>
                  <pre
                    style={{
                      padding: 'var(--space-3)',
                      background: 'var(--color-bg-base)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: 'var(--text-xs)',
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--color-text-primary)',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-all',
                      overflow: 'auto',
                      maxHeight: '300px',
                      margin: 0,
                    }}
                  >
                    {detail.request_body || '(empty)'}
                  </pre>
                </div>
                <div>
                  <div
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--color-text-muted)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      marginBottom: 'var(--space-2)',
                    }}
                  >
                    Response Body
                  </div>
                  <pre
                    style={{
                      padding: 'var(--space-3)',
                      background: 'var(--color-bg-base)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: 'var(--text-xs)',
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--color-text-primary)',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-all',
                      overflow: 'auto',
                      maxHeight: '300px',
                      margin: 0,
                    }}
                  >
                    {detail.response_body || '(empty)'}
                  </pre>
                </div>
              </div>
            )}

            {activeTab === 'headers' && (
              <div>
                <div style={{ marginBottom: 'var(--space-3)' }}>
                  <div
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--color-text-muted)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      marginBottom: 'var(--space-2)',
                    }}
                  >
                    Request Headers
                  </div>
                  <pre
                    style={{
                      padding: 'var(--space-3)',
                      background: 'var(--color-bg-base)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: 'var(--text-xs)',
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--color-text-primary)',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-all',
                      margin: 0,
                    }}
                  >
                    {formatHeaders(detail.request_headers)}
                  </pre>
                </div>
                <div>
                  <div
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--color-text-muted)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      marginBottom: 'var(--space-2)',
                    }}
                  >
                    Response Headers
                  </div>
                  <pre
                    style={{
                      padding: 'var(--space-3)',
                      background: 'var(--color-bg-base)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: 'var(--text-xs)',
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--color-text-primary)',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-all',
                      margin: 0,
                    }}
                  >
                    {formatHeaders(detail.response_headers)}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
