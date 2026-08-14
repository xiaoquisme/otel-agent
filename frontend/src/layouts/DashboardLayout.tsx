import { useState, useCallback } from 'react'
import { Outlet } from 'react-router-dom'

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
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="8" cy="8" r="6" />
            <path d="M8 5v3l2 2" />
          </svg>
          <h1 style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-semibold)' }}>
            otel-agent
          </h1>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
            trajectory
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
            ?
          </span>
        </div>
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
