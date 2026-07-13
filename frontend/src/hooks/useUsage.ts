import { useState, useEffect } from 'react'
import type { UsageSummary } from '../api/types'
import { fetchUsage } from '../api/client'

export function useUsage() {
  const [usage, setUsage] = useState<UsageSummary | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>

    async function load() {
      try {
        const now = new Date()
        const start = new Date(now.getFullYear(), now.getMonth(), now.getDate())
        const end = new Date(start)
        end.setDate(end.getDate() + 1)
        const data = await fetchUsage(
          start.toISOString().replace(/\.\d{3}Z$/, 'Z'),
          end.toISOString().replace(/\.\d{3}Z$/, 'Z'),
        )
        setUsage(data)
      } catch {}
      setLoading(false)
    }

    load()
    interval = setInterval(load, 30000)
    return () => clearInterval(interval)
  }, [])

  return { usage, loading }
}
