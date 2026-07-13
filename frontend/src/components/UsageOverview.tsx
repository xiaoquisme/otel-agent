import { useUsage } from '../hooks/useUsage'

function formatNumber(n: number | null | undefined): string {
  if (n == null) return '0'
  return Number(n).toLocaleString()
}

export default function UsageOverview() {
  const { usage, loading } = useUsage()

  if (loading) {
    return (
      <div className="px-6 py-4">
        <h2 className="text-sm font-semibold text-[#8b949e] uppercase tracking-wide mb-3">Usage Today</h2>
        <div className="text-[#8b949e] text-sm py-4 text-center">Loading usage data...</div>
      </div>
    )
  }

  if (!usage) return null

  return (
    <div className="px-6 py-4">
      <h2 className="text-sm font-semibold text-[#8b949e] uppercase tracking-wide mb-3">Usage Today</h2>
      <div className="grid grid-cols-3 gap-3 mb-4">
        <UsageCard label="Total Tokens" value={formatNumber(usage.total_tokens)} />
        <UsageCard label="Input Tokens" value={formatNumber(usage.input_tokens)} />
        <UsageCard label="Output Tokens" value={formatNumber(usage.output_tokens)} />
      </div>
      {usage.excluded_request_count > 0 && (
        <p className="text-xs text-[#8b949e] mb-2">
          <strong className="text-[#e1e4e8]">{formatNumber(usage.excluded_request_count)}</strong> request(s) excluded — no token data.
        </p>
      )}
      {usage.eligible_request_count === 0 && usage.excluded_request_count === 0 && (
        <p className="text-xs text-[#8b949e] italic">No requests with token data recorded today.</p>
      )}
      {usage.models && usage.models.length > 0 && (
        <div className="mt-4">
          <h3 className="text-xs text-[#8b949e] uppercase tracking-wide mb-2">Model Breakdown</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#30363d]">
                <th className="text-left py-1 px-2 text-[11px] text-[#8b949e] uppercase">#</th>
                <th className="text-left py-1 px-2 text-[11px] text-[#8b949e] uppercase">Model</th>
                <th className="text-right py-1 px-2 text-[11px] text-[#8b949e] uppercase">Total</th>
                <th className="text-right py-1 px-2 text-[11px] text-[#8b949e] uppercase">Requests</th>
                <th className="w-30 py-1 px-2"></th>
              </tr>
            </thead>
            <tbody>
              {usage.models.map((m, i) => {
                const maxTokens = usage.models[0].total_tokens || 1
                const pct = Math.round(((m.total_tokens || 0) / maxTokens) * 100)
                return (
                  <tr key={i} className="border-b border-[#21262d]">
                    <td className="py-1 px-2 text-[#8b949e] font-semibold">{i + 1}</td>
                    <td className="py-1 px-2 font-mono text-xs text-[#58a6ff]">{m.model_name || 'Unknown'}</td>
                    <td className="py-1 px-2 text-right tabular-nums">{formatNumber(m.total_tokens)}</td>
                    <td className="py-1 px-2 text-right text-[#8b949e]">{formatNumber(m.request_count)}</td>
                    <td className="py-1 px-2">
                      <div className="h-1.5 rounded bg-[#30363d] overflow-hidden">
                        <div className="h-full rounded bg-[#58a6ff]" style={{ width: `${pct}%` }} />
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function UsageCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
      <div className="text-[11px] text-[#8b949e] uppercase tracking-wide mb-1">{label}</div>
      <div className="text-2xl font-bold tabular-nums">{value}</div>
    </div>
  )
}
