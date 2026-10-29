import { useState, useEffect, useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchRequestDetail, downloadRequestJson } from '../api/client'
import type { RequestDetail } from '../api/types'
import { Skeleton, CodeBlock } from '../components/ui'
import { isInferredSession, sessionPath } from '../lib/session'
import { buildTrajectoryCells } from '../components/trajectory/buildTrajectoryCells'
import TrajectoryLedger from '../components/trajectory/TrajectoryLedger'
import TrajectoryOverview from '../components/trajectory/TrajectoryOverview'
import EventDetails from '../components/trajectory/EventDetails'
import TrajectorySplit from '../components/trajectory/TrajectorySplit'
import '../components/trajectory/trajectory.css'

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

  useEffect(() => {
    if (cells.length === 0) return
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
      const target = event.target
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement
      ) {
        return
      }
      if (target instanceof Element && target.closest('.dsh-ledger, .dsh-split-handle')) return
      const current = cells.findIndex((cell) => cell.id === selectedCellId)
      const next = event.key === 'ArrowDown'
        ? (current < 0 ? 0 : Math.min(cells.length - 1, current + 1))
        : Math.max(0, current < 0 ? 0 : current - 1)
      const id = cells[next]?.id
      if (!id) return
      event.preventDefault()
      setSelectedCellId(id)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [cells, selectedCellId])

  if (loading) {
    return (
      <div className="dsh-trajectory">
        <div className="dsh-loading">
          <Skeleton width="40%" height="14px" />
          <div style={{ height: 12 }} />
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="dsh-loading-row">
              <Skeleton width="100%" height="38px" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (!detail) {
    return (
      <div className="dsh-trajectory">
        <div className="dsh-missing">Request not found</div>
      </div>
    )
  }

  const totalTokens = detail.metadata?.usage?.total_tokens
  const statusBad = detail.response_status >= 400

  return (
    <div className="dsh-trajectory">
      <header className="dsh-header">
        <span className="dsh-method">{detail.method}</span>
        <span className="dsh-url" title={detail.url}>{detail.url}</span>
        <span className="dsh-meta">
          <span className={statusBad ? 'dsh-status dsh-status-bad' : 'dsh-status'}>
            {detail.response_status}
          </span>
          <span className="dsh-dot" aria-hidden="true">·</span>
          <span>{detail.latency_ms?.toFixed(0) ?? 0}ms</span>
          {detail.model_name && (
            <>
              <span className="dsh-dot" aria-hidden="true">·</span>
              <span className="dsh-model" title={detail.model_name}>{detail.model_name}</span>
            </>
          )}
          {totalTokens != null && (
            <>
              <span className="dsh-dot" aria-hidden="true">·</span>
              <span>{totalTokens.toLocaleString()} tok</span>
            </>
          )}
        </span>
        <button type="button" className="dsh-download" onClick={() => downloadRequestJson(detail)}>
          Download JSON
        </button>
      </header>

      {detail.session_id && (
        <div className="dsh-session">
          <span className="dsh-session-kicker">This request is one step in</span>
          <Link
            className="dsh-session-link"
            to={sessionPath(detail.session_id)}
            title={detail.session_id}
          >
            {detail.session_id}
          </Link>
          {detail.session_step && (
            <span className="dsh-session-badge" title="X-Otel-Session-Step">
              {detail.session_step}
            </span>
          )}
          {isInferredSession(detail.session_id) && (
            <span
              className="dsh-session-badge"
              title="No session header was sent. This id is a hash of the conversation root."
            >
              inferred
            </span>
          )}
        </div>
      )}

      {cells.length === 0 ? (
        <div className="dsh-fallback">
          <CodeBlock data={detail.request_body} title="Request body" />
          <div style={{ height: 12 }} />
          <CodeBlock data={detail.response_body} title="Response body" />
        </div>
      ) : (
        <>
          <TrajectoryOverview
            cells={cells}
            selectedId={selectedCellId}
            onSelect={setSelectedCellId}
          />
          <TrajectorySplit
            ledger={
              <TrajectoryLedger
                cells={cells}
                selectedId={selectedCellId}
                onSelect={setSelectedCellId}
              />
            }
            details={<EventDetails detail={detail} cell={selectedCell} />}
          />
        </>
      )}
    </div>
  )
}
