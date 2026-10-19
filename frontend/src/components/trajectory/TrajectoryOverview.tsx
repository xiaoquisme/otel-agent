import type { CSSProperties } from 'react'
import type { TrajectoryCell, TrajectoryKind } from './buildTrajectoryCells'
import './trajectory.css'

interface TrajectoryOverviewProps {
  cells: TrajectoryCell[]
  selectedId: string | null
  onSelect: (id: string) => void
}

/** Cap before the square root so one huge prompt cannot hide the other steps. */
const MAX_CHARS = 2000

/**
 * One logged request has a single latency_ms, so the strip cannot show real
 * per-step durations. Width is the square root of that step's text length.
 */
function stepWeight(cell: TrajectoryCell): number {
  const text = cell.toolCall
    ? `${cell.toolCall.name}${cell.toolCall.arguments}`
    : cell.kind === 'REASONING'
      ? (cell.message.reasoning_content ?? '')
      : (cell.message.content ?? '')
  const chars = Math.min(Math.max(text.length, 1), MAX_CHARS)
  return Math.sqrt(chars)
}

function placement(kind: TrajectoryKind): { lane: 0 | 1 | 2; span: string } {
  switch (kind) {
    case 'SYSTEM':
      return { lane: 0, span: 'system' }
    case 'USER':
      return { lane: 0, span: 'user' }
    case 'REASONING':
      return { lane: 1, span: 'reasoning' }
    case 'ASSISTANT':
      return { lane: 1, span: 'message' }
    case 'TOOL':
      return { lane: 2, span: 'tool' }
  }
}

export default function TrajectoryOverview({ cells, selectedId, onSelect }: TrajectoryOverviewProps) {
  const weights = cells.map(stepWeight)
  const total = weights.reduce((sum, weight) => sum + weight, 0) || 1
  let cursor = 0

  return (
    <div className="dsh-timeline">
      <div className="dsh-timeline-plot">
        <div className="dsh-timeline-labels" aria-hidden="true">
          <span>User</span>
          <span>Msg</span>
          <span>Tool</span>
        </div>
        <div className="dsh-timeline-track">
          <div className="dsh-timeline-lanes" role="group" aria-label="Trajectory overview">
            {cells.map((cell, index) => {
              const weight = weights[index]
              const left = (cursor / total) * 100
              const width = (weight / total) * 100
              cursor += weight
              const { lane, span } = placement(cell.kind)
              const current = cell.id === selectedId
              const style = {
                '--dsh-span-lane': String(lane),
                '--dsh-span-left': `${left}%`,
                '--dsh-span-width': `${width}%`,
              } as CSSProperties
              return (
                <span key={cell.id}>
                  {cell.kind === 'USER' && left > 0.4 && (
                    <span className="dsh-timeline-boundary" aria-hidden="true" style={{ left: `${left}%` }} />
                  )}
                  <button
                    type="button"
                    className="dsh-timeline-span"
                    data-span={span}
                    data-current={current ? 'true' : 'false'}
                    style={style}
                    aria-pressed={current}
                    aria-label={`${cell.kind} step ${cell.index}`}
                    title={`${cell.kind} ${cell.index}${cell.preview ? ` · ${cell.preview}` : ''}`}
                    onClick={() => onSelect(cell.id)}
                  />
                </span>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
