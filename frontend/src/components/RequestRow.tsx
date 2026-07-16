import type { RequestItem } from '../api/types'

interface RequestRowProps {
  request: RequestItem
  onClick: (id: number) => void
}

function getStatusClass(status: number): string {
  const prefix = Math.floor(status / 100)
  if (prefix === 2) return 'text-[#3fb950]'
  if (prefix === 4) return 'text-[#d29922]'
  if (prefix === 5) return 'text-[#f85149]'
  return 'text-[#e1e4e8]'
}

function getMethodClass(method: string): string {
  switch (method) {
    case 'GET': return 'bg-[#1f3a2e] text-[#3fb950]'
    case 'POST': return 'bg-[#2a1f3a] text-[#a371f7]'
    case 'PUT': return 'bg-[#3a2a1f] text-[#d29922]'
    case 'DELETE': return 'bg-[#3a1f1f] text-[#f85149]'
    default: return 'bg-[#21262d] text-[#8b949e]'
  }
}

export default function RequestRow({ request, onClick }: RequestRowProps) {
  return (
    <tr
      className="hover:bg-[#161b22] cursor-pointer"
      onClick={() => onClick(request.id)}
    >
      <td className="px-3 py-2.5 border-b border-[#21262d] text-sm">{request.id}</td>
      <td className="px-3 py-2.5 border-b border-[#21262d] text-sm">
        {new Date(request.timestamp).toLocaleString()}
      </td>
      <td className="px-3 py-2.5 border-b border-[#21262d]">
        <span className={`font-semibold text-xs px-1.5 py-0.5 rounded ${getMethodClass(request.method)}`}>
          {request.method}
        </span>
      </td>
      <td className="px-3 py-2.5 border-b border-[#21262d] text-sm max-w-[400px] overflow-hidden text-ellipsis whitespace-nowrap">
        {request.url}
      </td>
      <td className="px-3 py-2.5 border-b border-[#21262d]">
        <span className={getStatusClass(request.response_status)}>
          {request.response_status}
        </span>
      </td>
      <td className="px-3 py-2.5 border-b border-[#21262d] text-sm">
        {request.latency_ms != null ? `${request.latency_ms.toFixed(0)}ms` : '0ms'}
      </td>
      <td className="px-3 py-2.5 border-b border-[#21262d] text-sm text-[#8b949e] max-w-[150px] overflow-hidden text-ellipsis whitespace-nowrap">
        {request.model_name ?? '—'}
      </td>
    </tr>
  )
}
