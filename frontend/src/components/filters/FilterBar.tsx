import { useRef, useCallback } from 'react'

interface FilterBarProps {
  search: string
  method: string
  status: number
  total: number
  onSearchChange: (search: string) => void
  onMethodChange: (method: string) => void
  onStatusChange: (status: number) => void
}

export default function FilterBar({
  search,
  method,
  status,
  total,
  onSearchChange,
  onMethodChange,
  onStatusChange,
}: FilterBarProps) {
  const searchRef = useRef<HTMLInputElement>(null)

  const handleSearchKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onSearchChange('')
      searchRef.current?.blur()
    }
  }, [onSearchChange])

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        padding: 'var(--space-2) var(--space-4)',
        borderBottom: '1px solid var(--color-border-default)',
        background: 'var(--color-bg-surface)',
        flexShrink: 0,
      }}
    >
      {/* Search input */}
      <div style={{ position: 'relative', flex: '1 1 auto', maxWidth: '320px' }}>
        <svg
          width="14"
          height="14"
          viewBox="0 0 16 16"
          fill="none"
          stroke="var(--color-text-muted)"
          strokeWidth="1.5"
          style={{
            position: 'absolute',
            left: '8px',
            top: '50%',
            transform: 'translateY(-50%)',
            pointerEvents: 'none',
          }}
        >
          <circle cx="7" cy="7" r="5" />
          <path d="M11 11l3.5 3.5" />
        </svg>
        <input
          ref={searchRef}
          type="text"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          onKeyDown={handleSearchKeyDown}
          placeholder="Search... ( / )"
          style={{
            width: '100%',
            padding: '4px 8px 4px 28px',
            fontSize: 'var(--text-xs)',
            fontFamily: 'var(--font-mono)',
            background: 'var(--color-bg-base)',
            border: '1px solid var(--color-border-default)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--color-text-primary)',
            outline: 'none',
          }}
        />
      </div>

      {/* Method filter */}
      <select
        value={method}
        onChange={(e) => onMethodChange(e.target.value)}
        style={{
          padding: '4px 8px',
          fontSize: 'var(--text-xs)',
          fontFamily: 'var(--font-mono)',
          background: 'var(--color-bg-base)',
          border: '1px solid var(--color-border-default)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--color-text-primary)',
          outline: 'none',
          cursor: 'pointer',
        }}
      >
        <option value="">ALL</option>
        <option value="GET">GET</option>
        <option value="POST">POST</option>
        <option value="PUT">PUT</option>
        <option value="DELETE">DELETE</option>
      </select>

      {/* Status filter */}
      <select
        value={status}
        onChange={(e) => onStatusChange(Number(e.target.value))}
        style={{
          padding: '4px 8px',
          fontSize: 'var(--text-xs)',
          fontFamily: 'var(--font-mono)',
          background: 'var(--color-bg-base)',
          border: '1px solid var(--color-border-default)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--color-text-primary)',
          outline: 'none',
          cursor: 'pointer',
        }}
      >
        <option value={0}>ALL</option>
        <option value={200}>200</option>
        <option value={400}>400</option>
        <option value={404}>404</option>
        <option value={500}>500</option>
      </select>

      {/* Total count */}
      <div
        style={{
          marginLeft: 'auto',
          fontSize: 'var(--text-xs)',
          color: 'var(--color-text-secondary)',
          fontFamily: 'var(--font-mono)',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {total > 0 ? `${total.toLocaleString()} requests` : ''}
      </div>
    </div>
  )
}
