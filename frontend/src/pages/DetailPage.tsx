import { useState, useEffect, useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { fetchRequestDetail, downloadRequestJson } from '../api/client'
import type { RequestDetail } from '../api/types'
import { Skeleton, CodeBlock } from '../components/ui'
import { buildTrajectoryCells } from '../components/trajectory/buildTrajectoryCells'
import TrajectoryLedger from '../components/trajectory/TrajectoryLedger'
import EventDetails from '../components/trajectory/EventDetails'

export default function DetailPage() {
  const { id } = useParams<{ id: string }>()
  const [detail, setDetail] = useState<RequestDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    fetchRequestDetail(Number(id))
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false))
  }, [id])

  const cells = useMemo(
    () => (detail ? buildTrajectoryCells(detail.messages ?? []) : []),
    [detail],
  )

  useEffect(() => {
    if (cells.length === 0) {
      setSelectedCellId(null)
      return
    }
    setSelectedCellId((current) => current && cells.some((c) => c.id === current) ? current : cells[0].id)
  }, [cells])

  const selectedCell = cells.find((c) => c.id === selectedCellId) ?? null

  if (loading) {
    return (
      <div style={{ padding: 'var(--space-4)' }}>
        <Skeleton width="40%" height="18px" />
        <div style={{ marginTop: 'var(--space-4)' }}>
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} style={{ marginBottom: 'var(--space-2)' }}>
              <Skeleton width="100%" height="38px" />
            </div>
          ))}
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
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
        flex: 1,
        background: 'var(--color-bg-base)',
      }}
    >
      <header
        style={{
          flexShrink: 0,
          padding: 'var(--space-3) var(--space-4)',
          borderBottom: '1px solid var(--color-border-default)',
          background: 'var(--color-bg-surface)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-3)',
          flexWrap: 'wrap',
        }}
      >
        <span
          style={{
            fontWeight: 'var(--font-semibold)',
            fontSize: 'var(--text-xs)',
            padding: 'var(--space-1) var(--space-2)',
            borderRadius: 'var(--radius-sm)',
            background: detail.method === 'POST' ? 'var(--color-accent-purple-muted)' : 'var(--color-accent-green-muted)',
            color: detail.method === 'POST' ? 'var(--color-accent-purple)' : 'var(--color-accent-green)',
          }}
        >
          {detail.method}
        </span>
        <span style={{ fontSize: 'var(--text-sm)', wordBreak: 'break-all', flex: 1, minWidth: 0 }}>
          {detail.url}
        </span>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
          {detail.response_status} · {detail.latency_ms?.toFixed(0) ?? 0}ms
          {detail.model_name ? ` · ${detail.model_name}` : ''}
        </span>
        <button
          type="button"
          onClick={() => downloadRequestJson(detail)}
          style={{
            flexShrink: 0,
            fontSize: 'var(--text-xs)',
            color: 'var(--color-text-secondary)',
            background: 'var(--color-bg-base)',
            border: '1px solid var(--color-border-default)',
            borderRadius: 'var(--radius-sm)',
            padding: 'var(--space-1) var(--space-2)',
            cursor: 'pointer',
          }}
        >
          Download JSON
        </button>
      </header>

      {cells.length === 0 ? (
        <div style={{ flex: 1, overflow: 'auto', padding: 'var(--space-4)' }}>
          <CodeBlock data={detail.request_body} title="Request body" />
          <div style={{ height: 'var(--space-4)' }} />
          <CodeBlock data={detail.response_body} title="Response body" />
        </div>
      ) : (
        <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
          <div style={{ flex: '1 1 58%', minWidth: 0, display: 'flex', flexDirection: 'column' }}>
            <TrajectoryLedger
              cells={cells}
              selectedId={selectedCellId}
              onSelect={setSelectedCellId}
            />
          </div>
          <div
            style={{
              flex: '0 0 42%',
              minWidth: 280,
              borderLeft: '1px solid var(--color-border-default)',
            }}
          >
            <EventDetails detail={detail} cell={selectedCell} />
          </div>
        </div>
      )}
    </div>
  )
}
