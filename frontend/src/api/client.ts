import type { RequestDetail, RequestsResponse, UsageSummary, RequestListParams } from './types'

const API_BASE = '/api'

export async function fetchRequests(params: RequestListParams = {}): Promise<RequestsResponse> {
  const query = new URLSearchParams()
  if (params.search) query.set('search', params.search)
  if (params.method) query.set('method', params.method)
  if (params.status && params.status !== 0) query.set('status', String(params.status))
  if (params.cursor && params.cursor > 0) query.set('cursor', String(params.cursor))
  query.set('limit', String(params.limit ?? 50))

  const resp = await fetch(`${API_BASE}/requests?${query.toString()}`)
  if (!resp.ok) throw new Error(`Failed to fetch requests: ${resp.status}`)
  return resp.json() as Promise<RequestsResponse>
}

export async function fetchRequestDetail(id: number): Promise<RequestDetail> {
  const resp = await fetch(`${API_BASE}/requests/${id}`)
  if (!resp.ok) throw new Error(`Failed to fetch request detail: ${resp.status}`)
  return resp.json() as Promise<RequestDetail>
}

export async function fetchUsage(start: string, end: string): Promise<UsageSummary> {
  const query = new URLSearchParams({ start, end })
  const resp = await fetch(`${API_BASE}/usage?${query.toString()}`)
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: 'Failed to load usage' }))
    throw new Error(err.error || `Failed to fetch usage: ${resp.status}`)
  }
  return resp.json() as Promise<UsageSummary>
}

export function exportData(format: 'csv' | 'json', params: RequestListParams = {}): void {
  const query = new URLSearchParams()
  if (params.search) query.set('search', params.search)
  if (params.method) query.set('method', params.method)
  if (params.status && params.status !== 0) query.set('status', String(params.status))

  window.location.href = `${API_BASE}/export?format=${format}&${query.toString()}`
}

function maybeParseJson(value: unknown): unknown {
  if (typeof value !== 'string') return value
  const text = value.trim()
  if (!text) return value
  try {
    return JSON.parse(text)
  } catch {
    return value
  }
}

export function downloadRequestJson(detail: RequestDetail): void {
  const payload = {
    ...detail,
    request_body: maybeParseJson(detail.request_body),
    response_body: maybeParseJson(detail.response_body),
    request_headers: maybeParseJson(detail.request_headers),
    response_headers: maybeParseJson(detail.response_headers),
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `request-${detail.id}.json`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
