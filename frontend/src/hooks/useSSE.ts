import { useEffect, useRef } from 'react'
import type { RequestItem } from '../api/types'

export function useSSE(onNewRequest: (req: RequestItem) => void) {
  const onNewRequestRef = useRef(onNewRequest)
  onNewRequestRef.current = onNewRequest

  useEffect(() => {
    let es: EventSource | null = null
    let reconnectTimeout: ReturnType<typeof setTimeout>

    function connect() {
      es = new EventSource('/api/events')
      es.onmessage = (e) => {
        try {
          const req = JSON.parse(e.data) as RequestItem
          onNewRequestRef.current(req)
        } catch {}
      }
      es.onerror = () => {
        es?.close()
        reconnectTimeout = setTimeout(connect, 5000)
      }
    }

    connect()
    return () => {
      es?.close()
      clearTimeout(reconnectTimeout)
    }
  }, [])
}
