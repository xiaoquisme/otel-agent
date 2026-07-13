import { useState, useEffect, useRef, useCallback } from 'react'
import Header from './components/Header'
import RequestList from './components/RequestList'
import DetailPanel from './components/DetailPanel'
import ExportButtons from './components/ExportButtons'
import LatencyChart from './components/LatencyChart'
import UsageOverview from './components/UsageOverview'
import { useRequests } from './hooks/useRequests'
import type { RequestItem } from './api/types'

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
    prependRequest,
  } = useRequests()

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  // SSE real-time updates
  const connectSSE = useCallback(() => {
    const es = new EventSource('/api/events')
    es.onmessage = (e) => {
      try {
        const req: RequestItem = JSON.parse(e.data) as RequestItem
        // Only prepend if on first page with no filters
        if (search === '' && method === '' && status === 0) {
          prependRequest(req)
        }
      } catch {
        // ignore parse errors
      }
    }
    es.onerror = () => {
      es.close()
      setTimeout(connectSSE, 5000)
    }
    eventSourceRef.current = es
  }, [search, method, status, prependRequest])

  useEffect(() => {
    connectSSE()
    return () => {
      eventSourceRef.current?.close()
    }
  }, [connectSSE])

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
