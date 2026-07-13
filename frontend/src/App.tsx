import { useState } from 'react'
import Header from './components/Header'
import RequestList from './components/RequestList'
import DetailPanel from './components/DetailPanel'
import ExportButtons from './components/ExportButtons'
import LatencyChart from './components/LatencyChart'
import UsageOverview from './components/UsageOverview'
import { useRequests } from './hooks/useRequests'

export default function App() {
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

  const currentParams = { search, method, status }

  return (
    <div className="min-h-screen bg-[#0f1117] text-[#e1e4e8]">
      <Header requestCount={total} loading={loading} />

      <UsageOverview />

      <LatencyChart requests={requests} />

      <RequestList
        requests={requests}
        total={total}
        loading={loading}
        error={error}
        hasMore={hasMore}
        canGoBack={canGoBack}
        search={search}
        method={method}
        status={status}
        onSelectRequest={setSelectedId}
        onSearchChange={setSearch}
        onMethodChange={setMethod}
        onStatusChange={setStatus}
        onNextPage={goNext}
        onPrevPage={goPrev}
      />

      <div className="px-6 py-2 flex gap-3">
        <ExportButtons currentParams={currentParams} />
      </div>

      <DetailPanel requestId={selectedId} onClose={() => setSelectedId(null)} />
    </div>
  )
}
