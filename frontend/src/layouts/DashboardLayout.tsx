import { Outlet } from 'react-router-dom'

export default function DashboardLayout() {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--color-bg-base)', color: 'var(--color-text-primary)' }}>
      {/* Header */}
      <header
        style={{
          background: 'var(--color-bg-surface)',
          borderBottom: '1px solid var(--color-border-default)',
          padding: 'var(--space-4) var(--space-6)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <h1 style={{ fontSize: 'var(--text-lg)', fontWeight: 'var(--font-semibold)' }}>
          otel-agent Dashboard
        </h1>
        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
          {/* Request count will be added here */}
        </span>
      </header>

      {/* Main content */}
      <main style={{ padding: 'var(--space-6)' }}>
        <Outlet />
      </main>
    </div>
  )
}
