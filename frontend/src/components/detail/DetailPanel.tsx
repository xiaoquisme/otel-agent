import { useState, useEffect, useCallback } from 'react'
import { fetchRequestDetail } from '../../api/client'
import type { RequestDetail } from '../../api/types'
import { CloseIcon, Skeleton } from '../ui'
import DetailContent from './DetailContent'

interface DetailPanelProps {
  requestId: number | null
  onClose: () => void
}

export default function DetailPanel({ requestId, onClose }: DetailPanelProps) {
  const [detail, setDetail] = useState<RequestDetail | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (requestId === null) {
      setDetail(null)
      return
    }
    setLoading(true)
    fetchRequestDetail(requestId)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false))
  }, [requestId])

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose()
  }, [onClose])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const isOpen = requestId !== null

  if (!isOpen) return null

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--color-bg-surface)',
        overflow: 'hidden',
      }}
    >
      {/* Panel header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: 'var(--space-2) var(--space-3)',
          borderBottom: '1px solid var(--color-border-default)',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <span
            style={{
              fontSize: 'var(--text-xs)',
              fontFamily: 'var(--font-mono)',
              color: 'var(--color-text-secondary)',
            }}
          >
            #{requestId}
          </span>
          {detail && (
            <span
              style={{
                padding: '1px 4px',
                borderRadius: '3px',
                background: detail.method === 'POST' ? 'var(--color-accent-purple-muted)' : 'var(--color-accent-green-muted)',
                color: detail.method === 'POST' ? 'var(--color-accent-purple)' : 'var(--color-accent-green)',
                fontSize: '9px',
                fontWeight: 'var(--font-semibold)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {detail.method}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          aria-label="Close detail panel"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--color-text-secondary)',
            cursor: 'pointer',
            padding: 'var(--space-1)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            minWidth: '44px',
            minHeight: '44px',
          }}
        >
          <CloseIcon size={14} />
        </button>
      </div>

      {/* Loading skeleton */}
      {loading && (
        <div style={{ padding: 'var(--space-3)', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <Skeleton width="100%" height="16px" />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-2)' }}>
            <Skeleton height="32px" />
            <Skeleton height="32px" />
            <Skeleton height="32px" />
          </div>
          <Skeleton width="100%" height="60px" />
          <Skeleton width="100%" height="60px" />
        </div>
      )}

      {/* Content */}
      {!loading && detail && (
        <>
          {/* URL bar */}
          <div
            style={{
              padding: 'var(--space-2) var(--space-3)',
              borderBottom: '1px solid var(--color-border-muted)',
              fontSize: 'var(--text-xs)',
              fontFamily: 'var(--font-mono)',
              color: 'var(--color-text-secondary)',
              wordBreak: 'break-all',
              flexShrink: 0,
            }}
          >
            {detail.url}
          </div>

          {/* Shared detail content */}
          <div style={{ flex: 1, overflow: 'auto' }}>
            <DetailContent detail={detail} compact />
          </div>
        </>
      )}
    </div>
  )
}
