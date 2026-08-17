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
  return Number(n).toLocaleString()
}

export default function UsageOverview() {
  const [activePeriod, setActivePeriod] = useState<UsagePeriod>('today')
  const { usage, loading } = useUsage(activePeriod)

  return (
    <div style={{ padding: 'var(--space-4) 0' }}>
      {/* Period tabs */}
      <div style={{ display: 'flex', gap: 'var(--space-1)', marginBottom: 'var(--space-3)' }}>
        {PERIODS.map((p) => (
          <button
            key={p.key}
            onClick={() => setActivePeriod(p.key)}
            style={{
              padding: 'var(--space-1) var(--space-3)',
              fontSize: 'var(--text-xs)',
              fontWeight: activePeriod === p.key ? 'var(--font-semibold)' : 'var(--font-normal)',
              color: activePeriod === p.key ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
              background: activePeriod === p.key ? 'var(--color-bg-surface)' : 'transparent',
              border: '1px solid',
              borderColor: activePeriod === p.key ? 'var(--color-border-default)' : 'transparent',
              borderRadius: 'var(--radius-md)',
              cursor: 'pointer',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
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
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
            <UsageCard label="Total Tokens" value={formatNumber(usage.total_tokens)} />
            <UsageCard label="Input Tokens" value={formatNumber(usage.input_tokens)} />
            <UsageCard label="Output Tokens" value={formatNumber(usage.output_tokens)} />
          </div>
          {usage.excluded_request_count > 0 && (
            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginBottom: 'var(--space-2)' }}>
              <strong style={{ color: 'var(--color-text-primary)' }}>{formatNumber(usage.excluded_request_count)}</strong> request(s) excluded — no token data.
            </p>
          )}
          {usage.eligible_request_count === 0 && usage.excluded_request_count === 0 && (
            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', fontStyle: 'italic' }}>No requests with token data recorded for this period.</p>
          )}
          {usage.models && usage.models.length > 0 && (
            <div style={{ marginTop: 'var(--space-4)' }}>
              <h3 style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 'var(--space-2)' }}>
                Model Breakdown
              </h3>
              <table style={{ width: '100%', fontSize: 'var(--text-sm)' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--color-border-default)' }}>
                    <th style={{ textAlign: 'left', padding: 'var(--space-1) var(--space-2)', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', textTransform: 'uppercase' }}>#</th>
                    <th style={{ textAlign: 'left', padding: 'var(--space-1) var(--space-2)', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', textTransform: 'uppercase' }}>Model</th>
                    <th style={{ textAlign: 'right', padding: 'var(--space-1) var(--space-2)', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', textTransform: 'uppercase' }}>Total</th>
                    <th style={{ textAlign: 'right', padding: 'var(--space-1) var(--space-2)', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', textTransform: 'uppercase' }}>Requests</th>
                    <th style={{ width: '120px', padding: 'var(--space-1) var(--space-2)' }}></th>
                  </tr>
                </thead>
                <tbody>
                  {usage.models.map((m, i) => {
                    const maxTokens = usage.models[0].total_tokens || 1
                    const pct = Math.round(((m.total_tokens || 0) / maxTokens) * 100)
                    return (
                      <tr key={i} style={{ borderBottom: '1px solid var(--color-border-muted)' }}>
                        <td style={{ padding: 'var(--space-1) var(--space-2)', color: 'var(--color-text-secondary)', fontWeight: 'var(--font-semibold)' }}>{i + 1}</td>
                        <td style={{ padding: 'var(--space-1) var(--space-2)', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--color-accent-blue)' }}>{m.model_name || 'Unknown'}</td>
                        <td style={{ padding: 'var(--space-1) var(--space-2)', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{formatNumber(m.total_tokens)}</td>
                        <td style={{ padding: 'var(--space-1) var(--space-2)', textAlign: 'right', color: 'var(--color-text-secondary)' }}>{formatNumber(m.request_count)}</td>
                        <td style={{ padding: 'var(--space-1) var(--space-2)' }}>
                          <div style={{ height: '6px', borderRadius: 'var(--radius-full)', background: 'var(--color-bg-overlay)', overflow: 'hidden' }}>
                            <div style={{ height: '100%', borderRadius: 'var(--radius-full)', background: 'var(--color-accent-blue)', width: `${pct}%` }} />
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

function UsageCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: 'var(--color-bg-surface)', border: '1px solid var(--color-border-default)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-4)' }}>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 'var(--space-1)' }}>{label}</div>
      <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 'var(--font-bold)', fontVariantNumeric: 'tabular-nums' }}>{value}</div>
    </div>
  )
}
