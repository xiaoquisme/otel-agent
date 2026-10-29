import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchSessions } from '../api/client'
import type { SessionSummary } from '../api/types'
import { Badge } from '../components/ui'
import { isInferredSession, sessionPath } from '../lib/session'

const PAGE_SIZE = 50

function formatTokens(value: number | null | undefined): string {
  if (value == null) return '—'
  return value.toLocaleString()
}

function formatStamp(timestamp: string): string {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return timestamp
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export default function SessionsPage() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback((nextOffset: number) => {
    setLoading(true)
    setError(null)
    fetchSessions(nextOffset, PAGE_SIZE)
      .then((body) => {
        setSessions(body.data)
        setTotal(body.total)
        setOffset(body.offset)
        setHasMore(body.has_more)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to load sessions')
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load(0)
  }, [load])

  const openSession = (sessionId: string) => {
    navigate(sessionPath(sessionId))
  }

  return (
    <div style={{ flex: 1, overflow: 'auto', padding: 'var(--space-4)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 'var(--space-4)', marginBottom: 'var(--space-2)' }}>
        <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 'var(--font-semibold)', margin: 0 }}>
          Sessions
        </h2>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
          {total.toLocaleString()} {total === 1 ? 'session' : 'sessions'}
        </span>
      </div>
      <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginTop: 0, marginBottom: 'var(--space-4)' }}>
        One row groups every gateway call that shares a session id. Open a row to see those requests in time order.
        An <strong>inferred</strong> badge means the id came from the conversation root because no session header was sent.
      </p>

      {loading && <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>Loading sessions…</p>}
      {error && (
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-accent-red)' }} role="alert">{error}</p>
      )}

      {!loading && !error && sessions.length === 0 && (
        <div style={{
          background: 'var(--color-bg-surface)',
          border: '1px solid var(--color-border-default)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-6)',
          color: 'var(--color-text-secondary)',
          fontSize: 'var(--text-sm)',
        }}>
          No sessions yet. Tag agent traffic with the <code>X-Otel-Session</code> header (optional turn label: <code>X-Otel-Session-Step</code>). Requests without a session id stay in the request ledger.
        </div>
      )}

      {sessions.length > 0 && (
        <div style={{ overflowX: 'auto', border: '1px solid var(--color-border-default)', borderRadius: 'var(--radius-lg)', background: 'var(--color-bg-surface)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
            <thead>
              <tr style={{ textAlign: 'left', color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)' }}>
                <th style={thStyle}>Session</th>
                <th style={thStyle}>Requests</th>
                <th style={thStyle}>Tokens</th>
                <th style={thStyle} className="session-col-optional">Latency</th>
                <th style={thStyle} className="session-col-optional">Activity</th>
                <th style={thStyle} className="session-col-optional">Models</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((session) => {
                const partial = session.token_request_count < session.request_count
                return (
                  <tr
                    key={session.session_id}
                    onClick={() => openSession(session.session_id)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        openSession(session.session_id)
                      }
                    }}
                    tabIndex={0}
                    style={{ cursor: 'pointer', borderTop: '1px solid var(--color-border-muted)' }}
                  >
                    <td style={tdStyle}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-2)' }}>
                        <div style={{ flex: '1 1 auto', minWidth: 0, fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', wordBreak: 'break-all' }}>
                          {session.session_id}
                        </div>
                        {isInferredSession(session.session_id) && (
                          <Badge
                            variant="info"
                            size="sm"
                            title="Grouped from the conversation root because no session header was sent"
                          >
                            inferred
                          </Badge>
                        )}
                      </div>
                      {session.error_count > 0 && (
                        <div style={{ marginTop: 'var(--space-1)' }}>
                          <Badge variant="error" size="sm">{session.error_count} failed</Badge>
                        </div>
                      )}
                    </td>
                    <td style={tdStyle}>{session.request_count}</td>
                    <td style={tdStyle}>
                      <div>{formatTokens(session.total_tokens)}</div>
                      {partial && (
                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                          {session.token_request_count}/{session.request_count} reported
                        </div>
                      )}
                    </td>
                    <td style={tdStyle} className="session-col-optional">{formatLatency(session.total_latency_ms)}</td>
                    <td style={{ ...tdStyle, whiteSpace: 'nowrap' }} className="session-col-optional">
                      {formatStamp(session.first_timestamp)}
                      <div style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)' }}>
                        to {formatStamp(session.last_timestamp)}
                      </div>
                    </td>
                    <td style={{ ...tdStyle, color: 'var(--color-text-secondary)' }} className="session-col-optional">
                      {session.models.length > 0 ? session.models.join(', ') : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {(offset > 0 || hasMore) && (
        <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-3)' }}>
          <button type="button" disabled={offset === 0 || loading} onClick={() => load(Math.max(0, offset - PAGE_SIZE))} style={pagerStyle}>
            Previous
          </button>
          <button type="button" disabled={!hasMore || loading} onClick={() => load(offset + PAGE_SIZE)} style={pagerStyle}>
            Next
          </button>
        </div>
      )}
    </div>
  )
}

const thStyle: CSSProperties = {
  padding: 'var(--space-2) var(--space-3)',
  fontWeight: 'var(--font-medium)',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
}

const tdStyle: CSSProperties = {
  padding: 'var(--space-3)',
  verticalAlign: 'top',
}

const pagerStyle: CSSProperties = {
  fontSize: 'var(--text-xs)',
  padding: 'var(--space-1) var(--space-3)',
  borderRadius: 'var(--radius-sm)',
  border: '1px solid var(--color-border-default)',
  background: 'var(--color-bg-surface)',
  color: 'var(--color-text-primary)',
  cursor: 'pointer',
}
