import UsageOverview from '../components/UsageOverview'

export default function UsagePage() {
  return (
    <div style={{ flex: 1, overflow: 'auto', padding: 'var(--space-4)' }}>
      <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 'var(--font-semibold)', marginBottom: 'var(--space-4)' }}>
        Token Usage
      </h2>
      <UsageOverview />
    </div>
  )
}
