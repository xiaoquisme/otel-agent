import { useState, useEffect, useCallback, useRef } from 'react'
import type { RequestItem, RequestListParams } from '../api/types'
import { fetchRequests } from '../api/client'

export interface UseRequestsState {
  requests: RequestItem[]
  total: number
  loading: boolean
  error: string | null
  search: string
  method: string
  status: number
  hasMore: boolean
  canGoBack: boolean
}

export interface UseRequestsActions {
  setSearch: (search: string) => void
  setMethod: (method: string) => void
  setStatus: (status: number) => void
  goNext: () => void
  goPrev: () => void
  prependRequest: (req: RequestItem) => void
}

export function useRequests(): UseRequestsState & UseRequestsActions {
  const [requests, setRequests] = useState<RequestItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearchRaw] = useState('')
  const [method, setMethodRaw] = useState('')
  const [status, setStatusRaw] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [currentCursor, setCurrentCursor] = useState(0)
  const cursorStackRef = useRef<number[]>([])

  const doFetch = useCallback(async (params: RequestListParams) => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchRequests(params)
      setRequests(data.data)
      setTotal(data.total)
      setHasMore(data.has_more)
      setCurrentCursor(data.cursor)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  // Debounced search effect
  useEffect(() => {
    const timer = setTimeout(() => {
      cursorStackRef.current = []
      doFetch({ search, method, status, cursor: 0, limit: 50 })
    }, 300)
    return () => clearTimeout(timer)
  }, [search, doFetch])

  // Non-debounced effects for method/status
  useEffect(() => {
    cursorStackRef.current = []
    doFetch({ search, method, status, cursor: 0, limit: 50 })
  }, [method, status, doFetch])

  const setSearch = useCallback((v: string) => {
    setSearchRaw(v)
  }, [])

  const setMethod = useCallback((v: string) => {
    setMethodRaw(v)
  }, [])

  const setStatus = useCallback((v: number) => {
    setStatusRaw(v)
  }, [])

  const goNext = useCallback(() => {
    cursorStackRef.current.push(currentCursor)
    // The next_cursor from the last response drives the next fetch
    doFetch({ search, method, status, cursor: currentCursor, limit: 50 })
  }, [currentCursor, search, method, status, doFetch])

  const goPrev = useCallback(() => {
    const stack = cursorStackRef.current
    if (stack.length > 0) {
      const prevCursor = stack.pop()!
      doFetch({ search, method, status, cursor: prevCursor, limit: 50 })
    }
  }, [search, method, status, doFetch])

  const prependRequest = useCallback((req: RequestItem) => {
    setRequests((prev) => {
      const next = [req, ...prev]
      return next.length > 50 ? next.slice(0, 50) : next
    })
  }, [])

  return {
    requests,
    total,
    loading,
    error,
    search,
    method,
    status,
    hasMore,
    canGoBack: cursorStackRef.current.length > 0,
    setSearch,
    setMethod,
    setStatus,
    goNext,
    goPrev,
    prependRequest,
  }
}
