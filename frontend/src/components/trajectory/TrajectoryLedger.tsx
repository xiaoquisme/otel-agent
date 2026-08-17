import type { TrajectoryCell, TrajectoryKind } from './buildTrajectoryCells'

const kindStyle: Record<TrajectoryKind, { color: string; background: string }> = {
  SYSTEM: { color: 'var(--color-text-secondary)', background: 'var(--color-bg-muted)' },
  USER: { color: 'var(--color-accent-green)', background: 'var(--color-accent-green-muted)' },
  ASSISTANT: { color: 'var(--color-accent-blue)', background: 'var(--color-accent-blue-muted)' },
  TOOL: { color: 'var(--color-accent-yellow)', background: 'var(--color-accent-yellow-muted)' },
  REASONING: { color: 'var(--color-accent-purple)', background: 'var(--color-accent-purple-muted)' },
}

interface TrajectoryLedgerProps {
  cells: TrajectoryCell[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export default function TrajectoryLedger({ cells, selectedId, onSelect }: TrajectoryLedgerProps) {
  return (
    <div
      role="listbox"
      aria-label="Trajectory timeline"
      style={{
        flex: 1,
        overflow: 'auto',
        padding: 'var(--space-2)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)',
      }}
    >
      {cells.map((cell) => {
        const selected = cell.id === selectedId
        const tag = kindStyle[cell.kind]
        return (
          <button
            key={cell.id}
            type="button"
            role="option"
            aria-selected={selected}
            onClick={() => onSelect(cell.id)}
            style={{
              display: 'flex',
              alignItems: 'center',
              boxSizing: 'border-box',
              height: 38,
              padding: '0 8px 0 12px',
              gap: 16,
              borderRadius: 8,
              border: selected ? '2px solid var(--color-accent-blue)' : '1px solid var(--color-border-default)',
              background: 'var(--color-bg-elevated)',
              color: 'var(--color-text-primary)',
              cursor: 'pointer',
              minWidth: 0,
              width: '100%',
              textAlign: 'left',
            }}
          >
            <span style={{ flex: 'none', width: 24, fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}>
              {cell.index}
            </span>
            <span
              style={{
                flex: 'none',
                width: 88,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                height: 22,
                borderRadius: 6,
                fontSize: 'var(--text-xs)',
                fontWeight: 'var(--font-semibold)',
                color: tag.color,
                background: tag.background,
              }}
            >
              {cell.kind}
            </span>
            <span
              style={{
                flex: 1,
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                fontSize: 'var(--text-sm)',
              }}
            >
              {cell.preview || '(empty)'}
            </span>
          </button>
        )
      })}
    </div>
  )
}
