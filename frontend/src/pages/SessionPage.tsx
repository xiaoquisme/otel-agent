import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchSession } from '../api/client'
import type { SessionDetail, SessionStep, WasteFinding } from '../api/types'
import { Badge } from '../components/ui'
import { ArrowLeftIcon } from '../components/ui/icons'
import { openRequestWindow } from '../lib/openRequestWindow'
import { isInferredSession } from '../lib/session'

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
    second: '2-digit',
  })
}

function formatLatency(ms: number | null): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function endpointPath(url: string): string {
  try {
    const parsed = new URL(url)
    return parsed.pathname + parsed.search
  } catch {
    return url
  }
}

function statusColor(status: number | null): string {
  if (status == null) return 'var(--color-text-muted)'
  if (status >= 200 && status < 300) return 'var(--color-accent-green)'
  if (status >= 400 && status < 500) return 'var(--color-accent-yellow)'
  if (status >= 500) return 'var(--color-accent-red)'
  return 'var(--color-text-primary)'
}

function accentFor(step: SessionStep): string {
  if (step.flags.includes('failed')) return 'var(--color-accent-red)'
  if (step.flags.includes('slow')) return 'var(--color-accent-yellow)'
  return 'var(--color-accent-green)'
}

const RULE_LABELS: Record<string, string> = {
  failed_step: 'failed',
  slow_step: 'slow',
  retry_burst: 'retry',
  duplicate_call: 'duplicate',
  token_spike: 'token spike',
  heavy_context: 'heavy context',
}

function ruleLabel(ruleId: string): string {
  return RULE_LABELS[ruleId] ?? ruleId
}

function severitySummary(findings: WasteFinding[]): string {
  const warnings = findings.filter((finding) => finding.severity === 'warn').length
  const notes = findings.length - warnings
  const parts: string[] = []
  if (warnings > 0) parts.push(`${warnings} warning${warnings === 1 ? '' : 's'}`)
  if (notes > 0) parts.push(`${notes} note${notes === 1 ? '' : 's'}`)
  return parts.join(', ')
}

export default function SessionPage() {
  const params = useParams()
  const sessionId = params['*'] ?? ''
  const [session, setSession] = useState<SessionDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pinnedId, setPinnedId] = useState<number | null>(null)

  useEffect(() => {
    if (!sessionId) {
      setError('Session not found')
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    fetchSession(sessionId)
      .then(setSession)
      .catch((err: unknown) => {
        setSession(null)
        setError(err instanceof Error ? err.message : 'Failed to load session')
      })
      .finally(() => setLoading(false))
  }, [sessionId])

  return (
    <div style={{ flex: 1, overflow: 'auto', padding: 'var(--space-4)' }}>
      <Link
        to="/sessions"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 'var(--space-1)',
          fontSize: 'var(--text-xs)',
          color: 'var(--color-text-secondary)',
          textDecoration: 'none',
          marginBottom: 'var(--space-3)',
        }}
      >
        <ArrowLeftIcon size={14} />
        Sessions
      </Link>

      {loading && <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>Loading trajectory…</p>}
      {error && (
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-accent-red)' }} role="alert">{error}</p>
      )}

      {session && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap', margin: '0 0 var(--space-1)' }}>
            <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 'var(--font-semibold)', margin: 0, fontFamily: 'var(--font-mono)', wordBreak: 'break-all' }}>
              {session.session_id}
            </h2>
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
          <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginTop: 0 }}>
            {formatStamp(session.first_timestamp)} – {formatStamp(session.last_timestamp)}
            {session.models.length > 0 ? ` · ${session.models.join(', ')}` : ''}
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
            <Rollup label="Requests" value={String(session.request_count)} />
            <Rollup label="Total tokens" value={formatTokens(session.total_tokens)} />
            <Rollup label="Input" value={formatTokens(session.input_tokens)} />
            <Rollup label="Output" value={formatTokens(session.output_tokens)} />
            <Rollup label="Latency" value={formatLatency(session.total_latency_ms)} />
            <Rollup label="Failed" value={String(session.error_count)} />
          </div>
          {session.token_request_count < session.request_count && (
            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginTop: 0 }}>
              Token totals cover {session.token_request_count} of {session.request_count} steps. Steps without provider usage are left out of the sum.
            </p>
          )}

          <FindingsPanel
            findings={session.findings ?? []}
            onFocus={(requestId) => {
              setPinnedId(requestId)
              document.getElementById(`step-${requestId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
            }}
          />

          <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {session.steps.map((step, index) => (
              <li key={step.id} id={`step-${step.id}`} style={{ scrollMargin: 'var(--space-4)' }}>
                <button
                  type="button"
                  onClick={() => openRequestWindow(step.id)}
                  style={{
                    width: '100%',
                    textAlign: 'left',
                    background: pinnedId === step.id ? 'var(--color-bg-overlay)' : 'var(--color-bg-surface)',
                    border: pinnedId === step.id
                      ? '1px solid var(--color-accent-blue)'
                      : '1px solid var(--color-border-default)',
                    borderLeft: `3px solid ${accentFor(step)}`,
                    borderRadius: 'var(--radius-md)',
                    padding: 'var(--space-3)',
                    cursor: 'pointer',
                    color: 'inherit',
                    font: 'inherit',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'baseline', minWidth: 0 }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', width: '1.5rem' }}>
                        {String(index + 1).padStart(2, '0')}
                      </span>
                      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
                        {formatStamp(step.timestamp)}
                      </span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', fontWeight: 'var(--font-semibold)' }}>
                        {step.method}
                      </span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {endpointPath(step.url)}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', fontSize: 'var(--text-xs)' }}>
                      <span style={{ color: statusColor(step.response_status), fontWeight: 'var(--font-semibold)' }}>
                        {step.response_status ?? '—'}
                      </span>
                      <span style={{ color: 'var(--color-text-secondary)' }}>{formatLatency(step.latency_ms)}</span>
                      <span style={{ color: 'var(--color-text-secondary)' }}>
                        {formatTokens(step.total_tokens)} tok
                      </span>
                      <span style={{ color: 'var(--color-text-primary)', fontWeight: 'var(--font-medium)' }}>
                        cum {formatTokens(step.cumulative_total_tokens)}
                      </span>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', marginTop: 'var(--space-2)', flexWrap: 'wrap' }}>
                    {step.session_step && <Badge size="sm">{step.session_step}</Badge>}
                    {step.model_name && (
                      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>{step.model_name}</span>
                    )}
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                      in {formatTokens(step.input_tokens)} · out {formatTokens(step.output_tokens)}
                    </span>
                    {step.flags.includes('failed') && <Badge variant="error" size="sm">failed</Badge>}
                    {step.flags.includes('slow') && (
                      <Badge variant="warning" size="sm" title={`Latency at least ${formatLatency(session.slow_latency_ms)}`}>
                        slow
                      </Badge>
                    )}
                    {(step.waste_rules ?? [])
                      .filter((rule) => rule !== 'failed_step' && rule !== 'slow_step')
                      .map((rule) => (
                        <Badge key={rule} variant="warning" size="sm">{ruleLabel(rule)}</Badge>
                      ))}
                  </div>
                  {step.request_preview && (
                    <div style={{
                      marginTop: 'var(--space-2)',
                      fontFamily: 'var(--font-mono)',
                      fontSize: 'var(--text-xs)',
                      color: 'var(--color-text-secondary)',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}>
                      {step.request_preview}
                    </div>
                  )}
                </button>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  )
}

function FindingsPanel({
  findings,
  onFocus,
}: {
  findings: WasteFinding[]
  onFocus: (requestId: number) => void
}) {
  return (
    <section
      aria-label="Waste findings"
      style={{
        background: 'var(--color-bg-surface)',
        border: '1px solid var(--color-border-default)',
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-3)',
        marginBottom: 'var(--space-4)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          Waste findings
        </div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
          {findings.length === 0 ? 'None' : severitySummary(findings)}
        </div>
      </div>
      {findings.length === 0 ? (
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)', margin: 'var(--space-2) 0 0' }}>
          No waste findings on this trajectory.
        </p>
      ) : (
        <ul style={{ listStyle: 'none', margin: 'var(--space-2) 0 0', padding: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', maxHeight: 240, overflow: 'auto' }}>
          {findings.map((finding, index) => {
            const target = finding.request_ids[0]
            return (
              <li key={`${finding.rule_id}-${index}`}>
                <button
                  type="button"
                  disabled={target == null}
                  title={target != null ? 'Scroll to step' : undefined}
                  onClick={() => { if (target != null) onFocus(target) }}
                  style={{
                    width: '100%',
                    textAlign: 'left',
                    display: 'flex',
                    gap: 'var(--space-2)',
                    alignItems: 'baseline',
                    flexWrap: 'wrap',
                    background: 'transparent',
                    border: 'none',
                    padding: 0,
                    cursor: target == null ? 'default' : 'pointer',
                    color: 'inherit',
                    font: 'inherit',
                  }}
                >
                  <Badge variant={finding.rule_id === 'failed_step' ? 'error' : finding.severity === 'warn' ? 'warning' : 'info'} size="sm">
                    {ruleLabel(finding.rule_id)}
                  </Badge>
                  <span style={{ fontSize: 'var(--text-sm)', flex: '1 1 16rem' }}>{finding.message}</span>
                  {finding.tokens_involved != null && (
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
                      {formatTokens(finding.tokens_involved)} tok
                    </span>
                  )}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

function Rollup({ label, value }: { label: string; value: string }) {
  return (
    <div style={{
      background: 'var(--color-bg-surface)',
      border: '1px solid var(--color-border-default)',
      borderRadius: 'var(--radius-lg)',
      padding: 'var(--space-3)',
    }}>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        {label}
      </div>
      <div style={{ fontSize: 'var(--text-lg)', fontWeight: 'var(--font-semibold)', marginTop: 'var(--space-1)' }}>
        {value}
      </div>
    </div>
  )
}
