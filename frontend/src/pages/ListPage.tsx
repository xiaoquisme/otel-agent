import { useState } from 'react'
import { useRequests } from '../hooks/useRequests'
import { useKeyboard } from '../hooks/useKeyboard'
import FilterBar from '../components/filters/FilterBar'
import TimelineOverview from '../components/timeline/TimelineOverview'
import RequestLedger from '../components/ledger/RequestLedger'
import { openRequestWindow } from '../lib/openRequestWindow'

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

  useKeyboard({
    onSlash: () => {
      const searchInput = document.querySelector('input[type="text"]') as HTMLInputElement
      if (searchInput) {
        searchInput.focus()
      }
    },
  })

  const handleSelect = (id: number) => {
    setSelectedId(id)
  }

  const handleOpen = (id: number) => {
    setSelectedId(id)
    openRequestWindow(id)
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
      <FilterBar
        search={search}
        method={method}
        status={status}
        total={total}
        onSearchChange={setSearch}
        onMethodChange={setMethod}
        onStatusChange={setStatus}
      />

      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <TimelineOverview
          requests={requests}
          onRequestClick={handleOpen}
          selectedId={selectedId}
        />

        <RequestLedger
          requests={requests}
          loading={loading}
          error={error}
          hasMore={hasMore}
          canGoBack={canGoBack}
          selectedId={selectedId}
          onSelect={handleSelect}
          onOpen={handleOpen}
          onNextPage={goNext}
          onPrevPage={goPrev}
        />

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
          <span><kbd style={{ fontFamily: 'var(--font-mono)' }}>Enter</kbd> Open window</span>
        </div>
      </div>
    </div>
  )
}
