import { useEffect, useRef, type KeyboardEvent } from 'react'
import type { TrajectoryCell, TrajectoryKind } from './buildTrajectoryCells'
import './trajectory.css'

const kindClass: Record<TrajectoryKind, string> = {
  SYSTEM: 'dsh-tag-system',
  USER: 'dsh-tag-user',
  ASSISTANT: 'dsh-tag-assistant',
  TOOL: 'dsh-tag-tool',
  REASONING: 'dsh-tag-reasoning',
}

interface TrajectoryLedgerProps {
  cells: TrajectoryCell[]
  selectedId: string | null
  onSelect: (id: string) => void
}

function cellDomId(id: string): string {
  return `trajectory-cell-${id.replace(/[^A-Za-z0-9_-]/g, '_')}`
}

export default function TrajectoryLedger({ cells, selectedId, onSelect }: TrajectoryLedgerProps) {
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listRef.current?.focus({ preventScroll: true })
  }, [])

  useEffect(() => {
    if (!selectedId || !listRef.current) return
    const node = listRef.current.querySelector<HTMLElement>(
      `[data-cell-id="${CSS.escape(selectedId)}"]`,
    )
    node?.scrollIntoView({ block: 'nearest' })
  }, [selectedId])

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (cells.length === 0) return
    const current = cells.findIndex((cell) => cell.id === selectedId)
    let next = current
    if (event.key === 'ArrowDown') next = current < 0 ? 0 : Math.min(cells.length - 1, current + 1)
    else if (event.key === 'ArrowUp') next = Math.max(0, current < 0 ? 0 : current - 1)
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = cells.length - 1
    else return
    event.preventDefault()
    event.stopPropagation()
    const id = cells[next]?.id
    if (id) onSelect(id)
  }

  return (
    <div
      ref={listRef}
      className="dsh-ledger"
      role="listbox"
      tabIndex={0}
      aria-label="Trajectory timeline"
      aria-activedescendant={selectedId ? cellDomId(selectedId) : undefined}
      onKeyDown={onKeyDown}
    >
      {cells.map((cell) => {
        const selected = cell.id === selectedId
        const preview = cell.preview || '(empty)'
        return (
          <button
            key={cell.id}
            id={cellDomId(cell.id)}
            type="button"
            role="option"
            data-cell-id={cell.id}
            data-kind={cell.kind}
            aria-selected={selected}
            aria-posinset={cell.index}
            aria-setsize={cells.length}
            tabIndex={-1}
            className="dsh-cell"
            title={cell.preview || undefined}
            onClick={() => onSelect(cell.id)}
          >
            <span className="dsh-cell-index">{cell.index}</span>
            <span className="dsh-tag-slot">
              <span className={`dsh-tag ${kindClass[cell.kind]}`}>{cell.kind}</span>
            </span>
            <span className={cell.preview ? 'dsh-cell-text' : 'dsh-cell-text dsh-cell-text-empty'}>
              {preview}
            </span>
          </button>
        )
      })}
    </div>
  )
}
