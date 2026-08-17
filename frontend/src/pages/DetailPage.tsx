import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { fetchRequestDetail } from '../api/client'
import type { RequestDetail } from '../api/types'
import { Card, ArrowLeftIcon, Skeleton } from '../components/ui'
import DetailContent from '../components/detail/DetailContent'

export default function DetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<RequestDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    fetchRequestDetail(Number(id))
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false))
  }, [id])

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        navigate('/')
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [navigate])

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: 'var(--space-4)' }}>
        <Skeleton width="100px" height="14px" />
        <div style={{ marginTop: 'var(--space-4)' }}>
          <Card padding="lg">
            <Skeleton width="60%" height="20px" />
            <div style={{ marginTop: 'var(--space-3)' }}>
              <Skeleton width="100%" height="14px" />
            </div>
          </Card>
        </div>
        <div style={{ marginTop: 'var(--space-4)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 'var(--space-3)' }}>
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <div key={i} style={{ padding: 'var(--space-3)', background: 'var(--color-bg-elevated)', borderRadius: 'var(--radius-md)' }}>
                <Skeleton width="60%" height="10px" />
                <div style={{ marginTop: 'var(--space-1)' }}><Skeleton width="80%" height="14px" /></div>
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (!detail) {
    return (
      <div style={{ textAlign: 'center', padding: 'var(--space-12)', color: 'var(--color-text-secondary)' }}>
        Request not found
      </div>
    )
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
      {/* Back button */}
      <button
        onClick={() => navigate('/')}
        style={{
          background: 'none',
          border: 'none',
          color: 'var(--color-accent-blue)',
          cursor: 'pointer',
          fontSize: 'var(--text-sm)',
          marginBottom: 'var(--space-4)',
          padding: 0,
          display: 'inline-flex',
          alignItems: 'center',
          gap: 'var(--space-1)',
        }}
      >
        <ArrowLeftIcon size={14} /> Back to list
      </button>

      {/* Request Header */}
      <Card padding="lg" style={{ marginBottom: 'var(--space-4)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
          <span
            style={{
              fontWeight: 'var(--font-bold)',
              fontSize: 'var(--text-lg)',
              padding: 'var(--space-1) var(--space-2)',
              borderRadius: 'var(--radius-sm)',
              background: detail.method === 'POST' ? 'var(--color-accent-purple-muted)' : 'var(--color-accent-green-muted)',
              color: detail.method === 'POST' ? 'var(--color-accent-purple)' : 'var(--color-accent-green)',
            }}
          >
            {detail.method}
          </span>
          <span style={{ fontSize: 'var(--text-base)', wordBreak: 'break-all' }}>
            {detail.url}
          </span>
        </div>

        <div style={{ display: 'flex', gap: 'var(--space-4)', fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
          <span>Status: <strong style={{ color: 'var(--color-text-primary)' }}>{detail.response_status}</strong></span>
          <span>Latency: <strong style={{ color: 'var(--color-text-primary)' }}>{detail.latency_ms?.toFixed(0) ?? 0}ms</strong></span>
        </div>
      </Card>

      {/* Detail content */}
      <DetailContent detail={detail} />
    </div>
  )
}
