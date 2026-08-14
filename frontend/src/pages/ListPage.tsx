import { useState } from 'react'
import { useRequests } from '../hooks/useRequests'
import { useKeyboard } from '../hooks/useKeyboard'
import FilterBar from '../components/filters/FilterBar'
import TimelineOverview from '../components/timeline/TimelineOverview'
import RequestLedger from '../components/ledger/RequestLedger'
import DetailPanel from '../components/detail/DetailPanel'

export default function ListPage() {
  const {
    requests,
    total,
    loading,
    error,
    search,
    method,
    status,
    hasMore,
    canGoBack,
    setSearch,
    setMethod,
    setStatus,
    goNext,
    goPrev,
  } = useRequests()

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detailWidth] = useState(40)
  const [isResizing, setIsResizing] = useState(false)

  // Keyboard navigation
  useKeyboard({
    onSlash: () => {
      const searchInput = document.querySelector('input[type="text"]') as HTMLInputElement
      if (searchInput) {
        searchInput.focus()
      }
    },
  })

  const handleSelect = (id: number) => {
    setSelectedId(prev => prev === id ? null : id)
  }

  const handleCloseDetail = () => {
    setSelectedId(null)
  }

  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Filter bar */}
      <FilterBar
        search={search}
        method={method}
        status={status}
        total={total}
        onSearchChange={setSearch}
        onMethodChange={setMethod}
        onStatusChange={setStatus}
      />

      {/* Main content area */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          overflow: 'hidden',
        }}
      >
        {/* Left pane - timeline + ledger */}
        <div
          style={{
            flex: selectedId ? `1 1 ${100 - detailWidth}%` : '1 1 100%',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            minWidth: 0,
          }}
        >
          {/* Timeline overview */}
          <TimelineOverview
            requests={requests}
            onRequestClick={handleSelect}
            selectedId={selectedId}
          />

          {/* Request ledger */}
          <RequestLedger
            requests={requests}
            loading={loading}
            error={error}
            hasMore={hasMore}
            canGoBack={canGoBack}
            selectedId={selectedId}
            onSelect={handleSelect}
            onNextPage={goNext}
            onPrevPage={goPrev}
          />

          {/* Keyboard shortcuts */}
          <div
            style={{
              padding: 'var(--space-1) var(--space-3)',
              borderTop: '1px solid var(--color-border-default)',
              background: 'var(--color-bg-surface)',
              fontSize: 'var(--text-xs)',
              color: 'var(--color-text-muted)',
              display: 'flex',
              gap: 'var(--space-3)',
              flexShrink: 0,
            }}
          >
            <span><kbd style={{ fontFamily: 'var(--font-mono)' }}>↑↓</kbd> Navigate</span>
            <span><kbd style={{ fontFamily: 'var(--font-mono)' }}>/</kbd> Search</span>
            <span><kbd style={{ fontFamily: 'var(--font-mono)' }}>Esc</kbd> Close</span>
            <span><kbd style={{ fontFamily: 'var(--font-mono)' }}>Enter</kbd> Select</span>
          </div>
        </div>

        {/* Resize handle (only when detail is open) */}
        {selectedId && (
          <div
            onMouseDown={() => setIsResizing(true)}
            style={{
              width: '4px',
              cursor: 'col-resize',
              background: isResizing ? 'var(--color-accent-blue)' : 'var(--color-border-default)',
              transition: isResizing ? 'none' : 'background 0.15s',
              flexShrink: 0,
            }}
          />
        )}

        {/* Right pane - detail panel */}
        {selectedId && (
          <div
            style={{
              flex: `0 0 ${detailWidth}%`,
              overflow: 'hidden',
              minWidth: '300px',
            }}
          >
            <DetailPanel
              requestId={selectedId}
              onClose={handleCloseDetail}
            />
          </div>
        )}
      </div>
    </div>
  )
}
