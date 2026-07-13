import { useRequests } from '../hooks/useRequests'
import { useKeyboard } from '../hooks/useKeyboard'
import RequestTable from '../components/RequestTable'
import UsageOverview from '../components/UsageOverview'
import LatencyChart from '../components/LatencyChart'

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

  // Keyboard navigation
  useKeyboard({
    onSlash: () => {
      // Focus search input
      const searchInput = document.querySelector('input[type="text"]') as HTMLInputElement
      if (searchInput) {
        searchInput.focus()
      }
    },
  })

  return (
    <div>
      {/* Usage Overview */}
      <UsageOverview />

      {/* Latency Chart */}
      <LatencyChart requests={requests} />

      {/* Request Table */}
      <RequestTable
        requests={requests}
        total={total}
        loading={loading}
        error={error}
        hasMore={hasMore}
        canGoBack={canGoBack}
        search={search}
        method={method}
        status={status}
        onSearchChange={setSearch}
        onMethodChange={setMethod}
        onStatusChange={setStatus}
        onNextPage={goNext}
        onPrevPage={goPrev}
      />

      {/* Keyboard shortcuts help */}
      <div style={{ marginTop: 'var(--space-4)', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
        <span style={{ marginRight: 'var(--space-4)' }}>↑↓ Navigate</span>
        <span style={{ marginRight: 'var(--space-4)' }}>/ Focus search</span>
        <span>Esc Back</span>
      </div>
    </div>
  )
}
