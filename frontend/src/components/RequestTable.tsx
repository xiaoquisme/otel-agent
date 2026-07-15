import { useNavigate } from 'react-router-dom'
import type { RequestItem } from '../api/types'
import { SearchInput, Select } from './ui'

interface RequestTableProps {
  requests: RequestItem[]
  total: number
  loading: boolean
  error: string | null
  hasMore: boolean
  canGoBack: boolean
  search: string
  method: string
  status: number
  onSearchChange: (search: string) => void
  onMethodChange: (method: string) => void
  onStatusChange: (status: number) => void
  onNextPage: () => void
  onPrevPage: () => void
}

function getStatusColor(status: number): string {
  const prefix = Math.floor(status / 100)
  if (prefix === 2) return 'var(--color-accent-green)'
  if (prefix === 4) return 'var(--color-accent-yellow)'
  if (prefix === 5) return 'var(--color-accent-red)'
  return 'var(--color-text-primary)'
}

function getMethodColor(method: string): { bg: string; text: string } {
  switch (method) {
    case 'GET': return { bg: 'var(--color-accent-green-muted)', text: 'var(--color-accent-green)' }
    case 'POST': return { bg: 'var(--color-accent-purple-muted)', text: 'var(--color-accent-purple)' }
    case 'PUT': return { bg: 'var(--color-accent-yellow-muted)', text: 'var(--color-accent-yellow)' }
    case 'DELETE': return { bg: 'var(--color-accent-red-muted)', text: 'var(--color-accent-red)' }
    default: return { bg: 'var(--color-bg-overlay)', text: 'var(--color-text-secondary)' }
  }
}

export default function RequestTable({
  requests,
  total,
  loading,
  error,
  hasMore,
  canGoBack,
  search,
  method,
  status,
  onSearchChange,
  onMethodChange,
  onStatusChange,
  onNextPage,
  onPrevPage,
}: RequestTableProps) {
  const navigate = useNavigate()

  return (
    <div>
      {/* Filters */}
      <div style={{ display: 'flex', gap: 'var(--space-3)', marginBottom: 'var(--space-4)', flexWrap: 'wrap', alignItems: 'center' }}>
        <SearchInput
          value={search}
          onChange={onSearchChange}
          placeholder="Search URL or upstream..."
        />
        <Select value={method} onChange={(e) => onMethodChange(e.target.value)}>
          <option value="">All Methods</option>
          <option value="GET">GET</option>
          <option value="POST">POST</option>
          <option value="PUT">PUT</option>
          <option value="DELETE">DELETE</option>
        </Select>
        <Select
          value={status}
          onChange={(e) => onStatusChange(Number(e.target.value))}
        >
          <option value={0}>All Status</option>
          <option value={200}>200</option>
          <option value={400}>400</option>
          <option value={404}>404</option>
          <option value={500}>500</option>
        </Select>
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            background: 'var(--color-accent-red-muted)',
            border: '1px solid var(--color-accent-red)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-3)',
            marginBottom: 'var(--space-4)',
            fontSize: 'var(--text-sm)',
            color: 'var(--color-accent-red)',
          }}
        >
          {error}
        </div>
      )}

      {/* Table */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
          <thead>
            <tr>
              {['ID', 'Timestamp', 'Method', 'URL', 'Status', 'Latency', 'Model'].map((header) => (
                <th
                  key={header}
                  style={{
                    background: 'var(--color-bg-surface)',
                    textAlign: 'left',
                    padding: 'var(--space-2) var(--space-3)',
                    borderBottom: '2px solid var(--color-border-default)',
                    fontWeight: 'var(--font-semibold)',
                    color: 'var(--color-text-secondary)',
                    fontSize: 'var(--text-xs)',
                    textTransform: 'uppercase',
                  }}
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {requests.map((req) => {
              const methodColors = getMethodColor(req.method)
              return (
                <tr
                  key={req.id}
                  onClick={() => navigate(`/request/${req.id}`)}
                  style={{ cursor: 'pointer', transition: 'background var(--transition-fast)' }}
                  onMouseEnter={(e) => e.currentTarget.style.background = 'var(--color-bg-surface)'}
                  onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                >
                  <td style={{ padding: 'var(--space-2) var(--space-3)', borderBottom: '1px solid var(--color-border-muted)' }}>
                    {req.id}
                  </td>
                  <td style={{ padding: 'var(--space-2) var(--space-3)', borderBottom: '1px solid var(--color-border-muted)' }}>
                    {new Date(req.timestamp).toLocaleString()}
                  </td>
                  <td style={{ padding: 'var(--space-2) var(--space-3)', borderBottom: '1px solid var(--color-border-muted)' }}>
                    <span
                      style={{
                        fontWeight: 'var(--font-semibold)',
                        fontSize: 'var(--text-xs)',
                        padding: '2px 6px',
                        borderRadius: 'var(--radius-sm)',
                        background: methodColors.bg,
                        color: methodColors.text,
                      }}
                    >
                      {req.method}
                    </span>
                  </td>
                  <td
                    style={{
                      padding: 'var(--space-2) var(--space-3)',
                      borderBottom: '1px solid var(--color-border-muted)',
                      maxWidth: '400px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {req.url}
                  </td>
                  <td style={{ padding: 'var(--space-2) var(--space-3)', borderBottom: '1px solid var(--color-border-muted)' }}>
                    <span style={{ color: getStatusColor(req.response_status) }}>
                      {req.response_status}
                    </span>
                  </td>
                  <td style={{ padding: 'var(--space-2) var(--space-3)', borderBottom: '1px solid var(--color-border-muted)' }}>
                    {req.latency_ms != null ? `${req.latency_ms.toFixed(0)}ms` : '0ms'}
                  </td>
                  <td style={{ padding: 'var(--space-2) var(--space-3)', borderBottom: '1px solid var(--color-border-muted)', color: 'var(--color-text-secondary)', maxWidth: '150px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {req.model_name ?? '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {!loading && requests.length === 0 && (
          <div style={{ textAlign: 'center', padding: 'var(--space-12)', color: 'var(--color-text-secondary)' }}>
            No requests logged yet.
          </div>
        )}
      </div>

      {/* Pagination */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 'var(--space-4) 0' }}>
        <div style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-sm)' }}>
          {total > 0 ? `${total.toLocaleString()} total requests` : 'No results'}
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <button
            onClick={onPrevPage}
            disabled={!canGoBack}
            style={{
              background: 'var(--color-bg-overlay)',
              border: '1px solid var(--color-border-default)',
              color: 'var(--color-text-primary)',
              padding: 'var(--space-2) var(--space-3)',
              borderRadius: 'var(--radius-md)',
              fontSize: 'var(--text-sm)',
              cursor: canGoBack ? 'pointer' : 'not-allowed',
              opacity: canGoBack ? 1 : 0.5,
            }}
          >
            Prev
          </button>
          <button
            onClick={onNextPage}
            disabled={!hasMore}
            style={{
              background: 'var(--color-bg-overlay)',
              border: '1px solid var(--color-border-default)',
              color: 'var(--color-text-primary)',
              padding: 'var(--space-2) var(--space-3)',
              borderRadius: 'var(--radius-md)',
              fontSize: 'var(--text-sm)',
              cursor: hasMore ? 'pointer' : 'not-allowed',
              opacity: hasMore ? 1 : 0.5,
            }}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  )
}
