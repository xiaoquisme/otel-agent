import { useMemo } from 'react'
import type { RequestItem } from '../../api/types'

interface TimelineOverviewProps {
  requests: RequestItem[]
  onRequestClick: (id: number) => void
  selectedId?: number | null
}

function getMethodColor(method: string): string {
  switch (method) {
    case 'GET': return 'var(--color-accent-green)'
    case 'POST': return 'var(--color-accent-purple)'
    case 'PUT': return 'var(--color-accent-yellow)'
    case 'DELETE': return 'var(--color-accent-red)'
    default: return 'var(--color-text-secondary)'
  }
}

interface TimelineBar {
  id: number
  method: string
  status: number
  latency: number
  x: number
  width: number
}

export default function TimelineOverview({ requests, onRequestClick, selectedId }: TimelineOverviewProps) {
  const bars = useMemo<TimelineBar[]>(() => {
    if (requests.length === 0) return []

    const minTime = new Date(requests[0].timestamp).getTime()
    const maxTime = new Date(requests[requests.length - 1].timestamp).getTime()
    const timeRange = maxTime - minTime || 1

    return requests.map((req) => {
      const time = new Date(req.timestamp).getTime()
      const x = ((time - minTime) / timeRange) * 100
      return {
        id: req.id,
        method: req.method,
        status: req.response_status,
        latency: req.latency_ms ?? 0,
        x,
        width: Math.max(100 / requests.length, 2),
      }
    })
  }, [requests])

  if (requests.length === 0) {
    return (
      <div
        style={{
          height: '48px',
          borderBottom: '1px solid var(--color-border-default)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 'var(--text-xs)',
          color: 'var(--color-text-muted)',
        }}
      >
        No requests to display
      </div>
    )
  }

  return (
    <div
      style={{
        height: '48px',
        borderBottom: '1px solid var(--color-border-default)',
        background: 'var(--color-bg-base)',
        position: 'relative',
        overflow: 'hidden',
        cursor: 'pointer',
        flexShrink: 0,
      }}
    >
      {/* Timeline bars */}
      <div style={{ position: 'absolute', inset: '4px 0' }}>
        {bars.map((bar) => (
          <div
            key={bar.id}
            onClick={() => onRequestClick(bar.id)}
            title={`${bar.method} #${bar.id} — ${bar.status} — ${bar.latency}ms`}
            style={{
              position: 'absolute',
              left: `${bar.x}%`,
              bottom: 0,
              width: `${bar.width}%`,
              minWidth: '2px',
              height: '100%',
              background: getMethodColor(bar.method),
              opacity: selectedId === bar.id ? 1 : 0.6,
              border: selectedId === bar.id ? '1px solid var(--color-text-primary)' : 'none',
              borderRadius: '1px',
              transition: 'opacity 0.15s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.opacity = '1'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.opacity = selectedId === bar.id ? '1' : '0.6'
            }}
          />
        ))}
      </div>

      {/* Time labels */}
      <div
        style={{
          position: 'absolute',
          bottom: '2px',
          left: '4px',
          right: '4px',
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: '9px',
          color: 'var(--color-text-muted)',
          fontFamily: 'var(--font-mono)',
          fontVariantNumeric: 'tabular-nums',
          pointerEvents: 'none',
        }}
      >
        <span>{new Date(requests[0].timestamp).toLocaleTimeString()}</span>
        <span>{new Date(requests[requests.length - 1].timestamp).toLocaleTimeString()}</span>
      </div>
    </div>
  )
}
