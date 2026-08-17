import { useState } from 'react'
import { useUsage, type UsagePeriod } from '../hooks/useUsage'
import { Skeleton } from './ui'

const PERIODS: { key: UsagePeriod; label: string }[] = [
  { key: 'today', label: 'Today' },
  { key: 'week', label: 'This Week' },
  { key: 'month', label: 'This Month' },
  { key: 'all', label: 'All Time' },
]

function formatNumber(n: number | null | undefined): string {
  if (n == null) return '0'
  const num = Number(n)
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`
  return num.toLocaleString()
}

const MODEL_COLORS = [
  'var(--color-accent-blue)',
  'var(--color-accent-green)',
  'var(--color-accent-purple)',
  'var(--color-accent-yellow)',
  'var(--color-accent-red)',
]

export default function UsageOverview() {
  const [activePeriod, setActivePeriod] = useState<UsagePeriod>('today')
  const { usage, loading } = useUsage(activePeriod)

  return (
    <div style={{ padding: 'var(--space-4) 0' }}>
      {/* Period tabs */}
      <div style={{ display: 'flex', gap: '0', marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border-default)' }} role="tablist" aria-label="Usage time period">
        {PERIODS.map((p) => (
          <button
            key={p.key}
            onClick={() => setActivePeriod(p.key)}
            role="tab"
            aria-selected={activePeriod === p.key}
            style={{
              padding: 'var(--space-2) var(--space-3)',
              fontSize: 'var(--text-xs)',
              fontWeight: activePeriod === p.key ? 'var(--font-semibold)' : 'var(--font-normal)',
              color: activePeriod === p.key ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
              background: 'transparent',
              border: 'none',
              borderBottom: activePeriod === p.key ? '2px solid var(--color-accent-blue)' : '2px solid transparent',
              cursor: 'pointer',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              transition: 'color var(--transition-fast), border-color var(--transition-fast)',
            }}
          >
            {p.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{ background: 'var(--color-bg-surface)', border: '1px solid var(--color-border-default)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-4)' }}>
              <Skeleton width="60%" height="10px" />
              <div style={{ marginTop: 'var(--space-2)' }}>
                <Skeleton width="80%" height="24px" />
              </div>
            </div>
          ))}
        </div>
      ) : usage ? (
        <>
          {/* Summary cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
            <UsageCard label="Total Tokens" value={formatNumber(usage.total_tokens)} color="var(--color-accent-blue)" />
            <UsageCard label="Input Tokens" value={formatNumber(usage.input_tokens)} color="var(--color-accent-green)" />
            <UsageCard label="Output Tokens" value={formatNumber(usage.output_tokens)} color="var(--color-accent-purple)" />
          </div>

          {/* Request count summary */}
          <div style={{ display: 'flex', gap: 'var(--space-4)', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginBottom: 'var(--space-4)' }}>
            <span>
              <strong style={{ color: 'var(--color-text-primary)' }}>{formatNumber(usage.eligible_request_count)}</strong> requests with token data
            </span>
            {usage.excluded_request_count > 0 && (
              <span>
                <strong style={{ color: 'var(--color-accent-yellow)' }}>{formatNumber(usage.excluded_request_count)}</strong> excluded (no token data)
              </span>
            )}
          </div>

          {usage.eligible_request_count === 0 && usage.excluded_request_count === 0 && (
            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', fontStyle: 'italic', padding: 'var(--space-4) 0' }}>
              No requests with token data recorded for this period.
            </p>
          )}

          {/* Model breakdown */}
          {usage.models && usage.models.length > 0 && (
            <div style={{ marginTop: 'var(--space-2)' }}>
              <h3 style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 'var(--space-3)' }}>
                Model Breakdown
              </h3>

              {/* Stacked distribution bar */}
              <div style={{ display: 'flex', height: '8px', borderRadius: 'var(--radius-full)', overflow: 'hidden', marginBottom: 'var(--space-3)', background: 'var(--color-bg-overlay)' }}>
                {usage.models.map((m, i) => {
                  const totalAll = usage.models.reduce((sum, model) => sum + (model.total_tokens || 0), 0) || 1
                  const pct = ((m.total_tokens || 0) / totalAll) * 100
                  return (
                    <div
                      key={i}
                      title={`${m.model_name || 'Unknown'}: ${formatNumber(m.total_tokens)} tokens (${Math.round(pct)}%)`}
                      style={{
                        width: `${pct}%`,
                        background: MODEL_COLORS[i % MODEL_COLORS.length],
                        minWidth: pct > 0 ? '2px' : '0',
                      }}
                    />
                  )
                })}
              </div>

              {/* Model table */}
              <table style={{ width: '100%', fontSize: 'var(--text-sm)' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--color-border-default)' }}>
                    <th style={{ textAlign: 'left', padding: 'var(--space-1) var(--space-2)', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', textTransform: 'uppercase' }}>Model</th>
                    <th style={{ textAlign: 'right', padding: 'var(--space-1) var(--space-2)', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', textTransform: 'uppercase' }}>Total</th>
                    <th style={{ textAlign: 'right', padding: 'var(--space-1) var(--space-2)', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', textTransform: 'uppercase' }}>Requests</th>
                    <th style={{ width: '100px', padding: 'var(--space-1) var(--space-2)' }}></th>
                  </tr>
                </thead>
                <tbody>
                  {usage.models.map((m, i) => {
                    const maxTokens = usage.models[0].total_tokens || 1
                    const pct = Math.round(((m.total_tokens || 0) / maxTokens) * 100)
                    return (
                      <tr key={i} style={{ borderBottom: '1px solid var(--color-border-muted)' }}>
                        <td style={{ padding: 'var(--space-2)', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>
                          <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: 'var(--radius-full)', background: MODEL_COLORS[i % MODEL_COLORS.length], marginRight: 'var(--space-2)', verticalAlign: 'middle' }} />
                          <span style={{ color: 'var(--color-accent-blue)' }}>{m.model_name || 'Unknown'}</span>
                        </td>
                        <td style={{ padding: 'var(--space-2)', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{formatNumber(m.total_tokens)}</td>
                        <td style={{ padding: 'var(--space-2)', textAlign: 'right', color: 'var(--color-text-secondary)' }}>{formatNumber(m.request_count)}</td>
                        <td style={{ padding: 'var(--space-2)' }}>
                          <div style={{ height: '6px', borderRadius: 'var(--radius-full)', background: 'var(--color-bg-overlay)', overflow: 'hidden' }}>
                            <div style={{ height: '100%', borderRadius: 'var(--radius-full)', background: MODEL_COLORS[i % MODEL_COLORS.length], width: `${pct}%` }} />
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}
    </div>
  )
}

function UsageCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{
      background: 'var(--color-bg-surface)',
      border: '1px solid var(--color-border-default)',
      borderLeft: `3px solid ${color}`,
      borderRadius: 'var(--radius-lg)',
      padding: 'var(--space-4)',
    }}>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 'var(--space-1)' }}>{label}</div>
      <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 'var(--font-bold)', fontVariantNumeric: 'tabular-nums' }}>{value}</div>
    </div>
  )
}
