import { useRef, useCallback } from 'react'
import type { RequestItem } from '../../api/types'
import { Skeleton } from '../ui'

interface RequestLedgerProps {
  requests: RequestItem[]
  loading: boolean
  error: string | null
  hasMore: boolean
  canGoBack: boolean
  selectedId?: number | null
  onSelect: (id: number) => void
  onOpen?: (id: number) => void
  onNextPage: () => void
  onPrevPage: () => void
}

function getMethodColor(method: string): { bg: string; text: string } {
  switch (method) {
    case 'GET': return { bg: 'var(--color-accent-green-muted)', text: 'var(--color-accent-green)' }
    case 'POST': return { bg: 'var(--color-accent-purple-muted)', text: 'var(--color-accent-purple)' }
    case 'PUT': return { bg: 'var(--color-accent-yellow-muted)', text: 'var(--color-accent-yellow)' }
    case 'DELETE': return { bg: 'var(--color-accent-red-muted)', text: 'var(--color-accent-red)' }
    default: return { bg: 'var(--color-bg-overlay)', text: 'var(--color-text-secondary)' }
  }
}

function getStatusColor(status: number): string {
  const prefix = Math.floor(status / 100)
  if (prefix === 2) return 'var(--color-accent-green)'
  if (prefix === 4) return 'var(--color-accent-yellow)'
  if (prefix === 5) return 'var(--color-accent-red)'
  return 'var(--color-text-primary)'
}

function formatLatency(ms: number | null): string {
  if (ms === null) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  const h = String(date.getHours()).padStart(2, '0')
  const m = String(date.getMinutes()).padStart(2, '0')
  const s = String(date.getSeconds()).padStart(2, '0')
  return `${h}:${m}:${s}`
}

function getUrlPath(url: string): string {
  try {
    const parsed = new URL(url)
    return parsed.pathname + parsed.search
  } catch {
    return url
  }
}

export default function RequestLedger({
  requests,
  loading,
  error,
  hasMore,
  canGoBack,
  selectedId,
  onSelect,
  onOpen,
  onNextPage,
  onPrevPage,
}: RequestLedgerProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    const currentIndex = requests.findIndex(r => r.id === selectedId)
    if (e.key === 'ArrowDown' || e.key === 'j') {
      e.preventDefault()
      const nextIndex = currentIndex + 1
      if (nextIndex < requests.length) {
        onSelect(requests[nextIndex].id)
      } else if (hasMore) {
        onNextPage()
      }
    } else if (e.key === 'ArrowUp' || e.key === 'k') {
      e.preventDefault()
      const prevIndex = currentIndex - 1
      if (prevIndex >= 0) {
        onSelect(requests[prevIndex].id)
      } else if (canGoBack) {
        onPrevPage()
      }
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (selectedId !== null && selectedId !== undefined) {
        (onOpen ?? onSelect)(selectedId)
      }
    }
  }, [requests, selectedId, onSelect, onOpen, hasMore, canGoBack, onNextPage, onPrevPage])

  return (
    <div
      ref={containerRef}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      role="listbox"
      aria-label="Request list"
      aria-activedescendant={selectedId ? `request-row-${selectedId}` : undefined}
      style={{
        flex: 1,
        overflow: 'auto',
        outline: 'none',
      }}
    >
      {/* Table header */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '36px 60px 50px 56px 1fr 60px 60px 100px',
          gap: '0',
          padding: '0 var(--space-3)',
          height: '28px',
          alignItems: 'center',
          borderBottom: '1px solid var(--color-border-default)',
          background: 'var(--color-bg-surface)',
          position: 'sticky',
          top: 0,
          zIndex: 2,
          fontSize: 'var(--text-xs)',
          color: 'var(--color-text-secondary)',
          fontFamily: 'var(--font-mono)',
          fontWeight: 'var(--font-medium)',
        }}
      >
        <span>#</span>
        <span>Time</span>
        <span></span>
        <span>Status</span>
        <span>URL</span>
        <span style={{ textAlign: 'right' }}>Latency</span>
        <span style={{ textAlign: 'right' }}>Tokens</span>
        <span>Model</span>
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            padding: 'var(--space-3)',
            margin: 'var(--space-2)',
            background: 'var(--color-accent-red-muted)',
            border: '1px solid var(--color-accent-red)',
            borderRadius: 'var(--radius-sm)',
            fontSize: 'var(--text-xs)',
            color: 'var(--color-accent-red)',
          }}
        >
          {error}
        </div>
      )}

      {/* Loading skeleton */}
      {loading && requests.length === 0 && (
        <div style={{ padding: '0 var(--space-3)' }}>
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              style={{
                display: 'grid',
                gridTemplateColumns: '36px 60px 50px 56px 1fr 60px 60px 100px',
                gap: '0',
                height: '30px',
                alignItems: 'center',
                borderBottom: '1px solid var(--color-border-muted)',
              }}
            >
              <Skeleton width="20px" height="10px" />
              <Skeleton width="48px" height="10px" />
              <Skeleton width="36px" height="14px" />
              <Skeleton width="28px" height="10px" />
              <Skeleton width="80%" height="10px" />
              <Skeleton width="40px" height="10px" />
              <Skeleton width="30px" height="10px" />
              <Skeleton width="70px" height="10px" />
            </div>
          ))}
        </div>
      )}

      {/* Empty */}
      {!loading && requests.length === 0 && !error && (
        <div
          style={{
            padding: 'var(--space-8)',
            textAlign: 'center',
            fontSize: 'var(--text-xs)',
            color: 'var(--color-text-muted)',
          }}
        >
          No requests found.
        </div>
      )}

      {/* Rows */}
      {requests.map((req) => {
        const methodColors = getMethodColor(req.method)
        const isSelected = req.id === selectedId
        const urlPath = getUrlPath(req.url)
        const model = req.model_name ?? '—'

        return (
          <div
            key={req.id}
            id={`request-row-${req.id}`}
            role="option"
            aria-selected={isSelected}
            onClick={() => {
              onSelect(req.id)
              onOpen?.(req.id)
            }}
            style={{
              display: 'grid',
              gridTemplateColumns: '36px 60px 50px 56px 1fr 60px 60px 100px',
              gap: '0',
              padding: '0 var(--space-3)',
              height: '36px',
              alignItems: 'center',
              borderBottom: '1px solid var(--color-border-muted)',
              background: isSelected ? 'var(--color-accent-blue-muted)' : 'transparent',
              cursor: 'pointer',
              transition: 'background 0.1s',
              fontSize: 'var(--text-xs)',
              fontFamily: 'var(--font-mono)',
              fontVariantNumeric: 'tabular-nums',
            }}
            onMouseEnter={(e) => {
              if (!isSelected) e.currentTarget.style.background = 'var(--color-bg-surface)'
            }}
            onMouseLeave={(e) => {
              if (!isSelected) e.currentTarget.style.background = 'transparent'
            }}
          >
            {/* Index */}
            <span style={{ color: 'var(--color-text-muted)' }}>{req.id}</span>

            {/* Time */}
            <span style={{ color: 'var(--color-text-secondary)' }}>
              {formatTime(req.timestamp)}
            </span>

            {/* Method tag */}
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '1px 4px',
                borderRadius: '3px',
                background: methodColors.bg,
                color: methodColors.text,
                fontSize: '9px',
                fontWeight: 'var(--font-semibold)',
                letterSpacing: '0.03em',
                width: 'fit-content',
              }}
            >
              {req.method}
            </span>

            {/* Status */}
            <span style={{ color: getStatusColor(req.response_status) }}>
              {req.response_status}
            </span>

            {/* URL */}
            <span
              style={{
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                color: 'var(--color-text-primary)',
              }}
            >
              {urlPath}
            </span>

            {/* Latency */}
            <span style={{ textAlign: 'right', color: 'var(--color-text-secondary)' }}>
              {formatLatency(req.latency_ms)}
            </span>

            {/* Tokens (placeholder - would need usage data) */}
            <span style={{ textAlign: 'right', color: 'var(--color-text-muted)' }}>
              —
            </span>

            {/* Model */}
            <span
              style={{
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                color: 'var(--color-text-secondary)',
                fontSize: '10px',
              }}
            >
              {model}
            </span>
          </div>
        )
      })}

      {/* Pagination */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: 'var(--space-2) var(--space-3)',
          borderTop: '1px solid var(--color-border-default)',
          background: 'var(--color-bg-surface)',
        }}
      >
        <button
          onClick={onPrevPage}
          disabled={!canGoBack}
          style={{
            padding: '2px 8px',
            fontSize: 'var(--text-xs)',
            background: 'var(--color-bg-overlay)',
            border: '1px solid var(--color-border-default)',
            borderRadius: 'var(--radius-sm)',
            color: canGoBack ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
            cursor: canGoBack ? 'pointer' : 'not-allowed',
            opacity: canGoBack ? 1 : 0.5,
          }}
        >
          Prev
        </button>
        <button
          onClick={onNextPage}
          disabled={!hasMore}
          style={{
            padding: '2px 8px',
            fontSize: 'var(--text-xs)',
            background: 'var(--color-bg-overlay)',
            border: '1px solid var(--color-border-default)',
            borderRadius: 'var(--radius-sm)',
            color: hasMore ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
            cursor: hasMore ? 'pointer' : 'not-allowed',
            opacity: hasMore ? 1 : 0.5,
          }}
        >
          Next
        </button>
      </div>
    </div>
  )
}
