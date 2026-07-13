import type { RequestItem } from '../api/types'
import RequestRow from './RequestRow'

interface RequestListProps {
  requests: RequestItem[]
  total: number
  loading: boolean
  error: string | null
  hasMore: boolean
  canGoBack: boolean
  search: string
  method: string
  status: number
  onSelectRequest: (id: number) => void
  onSearchChange: (search: string) => void
  onMethodChange: (method: string) => void
  onStatusChange: (status: number) => void
  onNextPage: () => void
  onPrevPage: () => void
}

export default function RequestList({
  requests,
  total,
  loading,
  error,
  hasMore,
  canGoBack,
  search,
  method,
  status,
  onSelectRequest,
  onSearchChange,
  onMethodChange,
  onStatusChange,
  onNextPage,
  onPrevPage,
}: RequestListProps) {
  return (
    <>
      {/* Controls */}
      <div className="px-6 py-4 flex gap-3 flex-wrap items-center">
        <input
          type="text"
          className="bg-[#161b22] border border-[#30363d] text-[#e1e4e8] px-3 py-2 rounded-md text-sm min-w-[250px]"
          placeholder="Search URL or upstream..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        <select
          className="bg-[#161b22] border border-[#30363d] text-[#e1e4e8] px-3 py-2 rounded-md text-sm min-w-[120px]"
          value={method}
          onChange={(e) => onMethodChange(e.target.value)}
        >
          <option value="">All Methods</option>
          <option value="GET">GET</option>
          <option value="POST">POST</option>
          <option value="PUT">PUT</option>
          <option value="DELETE">DELETE</option>
        </select>
        <select
          className="bg-[#161b22] border border-[#30363d] text-[#e1e4e8] px-3 py-2 rounded-md text-sm min-w-[120px]"
          value={status}
          onChange={(e) => onStatusChange(Number(e.target.value))}
        >
          <option value={0}>All Status</option>
          <option value={200}>200</option>
          <option value={400}>400</option>
          <option value={404}>404</option>
          <option value={500}>500</option>
        </select>
      </div>

      {/* Error */}
      {error && (
        <div className="mx-6 mb-4 bg-[#1c1410] border border-[#d29922] rounded-md px-3 py-2 text-sm text-[#d29922]">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="px-6 overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr>
              <th className="bg-[#161b22] text-left px-3 py-2.5 border-b-2 border-[#30363d] font-semibold text-[#8b949e] text-xs uppercase">
                ID
              </th>
              <th className="bg-[#161b22] text-left px-3 py-2.5 border-b-2 border-[#30363d] font-semibold text-[#8b949e] text-xs uppercase">
                Timestamp
              </th>
              <th className="bg-[#161b22] text-left px-3 py-2.5 border-b-2 border-[#30363d] font-semibold text-[#8b949e] text-xs uppercase">
                Method
              </th>
              <th className="bg-[#161b22] text-left px-3 py-2.5 border-b-2 border-[#30363d] font-semibold text-[#8b949e] text-xs uppercase">
                URL
              </th>
              <th className="bg-[#161b22] text-left px-3 py-2.5 border-b-2 border-[#30363d] font-semibold text-[#8b949e] text-xs uppercase">
                Status
              </th>
              <th className="bg-[#161b22] text-left px-3 py-2.5 border-b-2 border-[#30363d] font-semibold text-[#8b949e] text-xs uppercase">
                Latency
              </th>
            </tr>
          </thead>
          <tbody>
            {requests.map((req) => (
              <RequestRow key={req.id} request={req} onClick={onSelectRequest} />
            ))}
          </tbody>
        </table>
        {!loading && requests.length === 0 && (
          <div className="text-center py-16 text-[#8b949e]">No requests logged yet.</div>
        )}
      </div>

      {/* Pagination */}
      <div className="px-6 py-4 flex justify-between items-center">
        <div className="text-[#8b949e] text-[13px]">
          {total > 0 ? `${total.toLocaleString()} total requests` : 'No results'}
        </div>
        <div className="flex gap-2">
          <button
            className="bg-[#21262d] border border-[#30363d] text-[#e1e4e8] px-3 py-1.5 rounded text-sm cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed hover:bg-[#30363d]"
            disabled={!canGoBack}
            onClick={onPrevPage}
          >
            Prev
          </button>
          <button
            className="bg-[#21262d] border border-[#30363d] text-[#e1e4e8] px-3 py-1.5 rounded text-sm cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed hover:bg-[#30363d]"
            disabled={!hasMore}
            onClick={onNextPage}
          >
            Next
          </button>
        </div>
      </div>
    </>
  )
}
