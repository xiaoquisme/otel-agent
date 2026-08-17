import { useState, useCallback } from 'react'
import { Outlet, NavLink } from 'react-router-dom'
import { ClockIcon } from '../components/ui'

const navLinkStyle = ({ isActive }: { isActive: boolean }): React.CSSProperties => ({
  fontSize: 'var(--text-xs)',
  fontWeight: isActive ? 'var(--font-semibold)' : 'var(--font-normal)',
  color: isActive ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
  textDecoration: 'none',
  padding: 'var(--space-1) var(--space-2)',
  borderRadius: 'var(--radius-sm)',
  background: isActive ? 'var(--color-bg-overlay)' : 'transparent',
  transition: 'background var(--transition-fast), color var(--transition-fast)',
})

export default function DashboardLayout() {
  const [detailPanelWidth, setDetailPanelWidth] = useState(40)
  const [isResizing, setIsResizing] = useState(false)

  const handleMouseDown = useCallback(() => {
    setIsResizing(true)
  }, [])

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isResizing) return
    const container = document.getElementById('split-pane-container')
    if (!container) return
    const rect = container.getBoundingClientRect()
    const percentage = ((rect.right - e.clientX) / rect.width) * 100
    setDetailPanelWidth(Math.min(Math.max(percentage, 20), 60))
  }, [isResizing])

  const handleMouseUp = useCallback(() => {
    setIsResizing(false)
  }, [])

  // Attach global mouse events for resize
  if (isResizing) {
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
  }

  return (
    <div
      id="split-pane-container"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        background: 'var(--color-bg-base)',
        color: 'var(--color-text-primary)',
      }}
    >
      {/* Header */}
      <header
        style={{
          background: 'var(--color-bg-surface)',
          borderBottom: '1px solid var(--color-border-default)',
          padding: 'var(--space-2) var(--space-4)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          <ClockIcon size={16} />
          <h1 style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-semibold)', margin: 0 }}>
            otel-agent
          </h1>
        </div>
        <nav style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-1)' }} aria-label="Main navigation">
          <NavLink to="/" end style={navLinkStyle}>Requests</NavLink>
          <NavLink to="/usage" style={navLinkStyle}>Usage</NavLink>
        </nav>
      </header>

      {/* Main content - split pane */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        {/* Left pane - table area */}
        <div
          style={{
            flex: `1 1 ${100 - detailPanelWidth}%`,
            display: 'flex',
            flexDirection: 'column',
            minWidth: 0,
            overflow: 'hidden',
          }}
        >
          <Outlet />
        </div>

        {/* Resize handle */}
        <div
          onMouseDown={handleMouseDown}
          style={{
            width: '4px',
            cursor: 'col-resize',
            background: isResizing ? 'var(--color-accent-blue)' : 'var(--color-border-default)',
            transition: isResizing ? 'none' : 'background 0.15s',
            flexShrink: 0,
          }}
        />

        {/* Right pane - detail panel (placeholder for now) */}
        <div
          id="detail-panel"
          style={{
            flex: `0 0 ${detailPanelWidth}%`,
            borderLeft: '1px solid var(--color-border-default)',
            background: 'var(--color-bg-surface)',
            overflow: 'auto',
            display: 'none', /* Will be shown when a request is selected */
          }}
        />
      </div>
    </div>
  )
}
