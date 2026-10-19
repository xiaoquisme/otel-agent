import { useState, useEffect } from 'react'
import type { UsageBucket, UsageSeries, UsageSummary } from '../api/types'
import { fetchUsage, fetchUsageSeries } from '../api/client'

export type UsagePeriod = 'today' | 'week' | 'month' | 'all'

export function bucketForPeriod(period: UsagePeriod): UsageBucket | undefined {
  if (period === 'today') return 'hour'
  if (period === 'week' || period === 'month') return 'day'
  return undefined
}

export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

function toUTC(d: Date): string {
  return d.toISOString().replace(/\.\\d{3}Z$/, 'Z')
}

function getRange(period: UsagePeriod): { start: string; end: string } {
  const now = new Date()

  if (period === 'today') {
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const end = new Date(start)
    end.setDate(end.getDate() + 1)
    return { start: toUTC(start), end: toUTC(end) }
  }

  if (period === 'week') {
    // Week starts on Monday
    const day = now.getDay()
    const diff = day === 0 ? 6 : day - 1 // days since Monday
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - diff)
    const end = new Date(start)
    end.setDate(end.getDate() + 7)
    return { start: toUTC(start), end: toUTC(end) }
  }

  if (period === 'month') {
    const start = new Date(now.getFullYear(), now.getMonth(), 1)
    const end = new Date(now.getFullYear(), now.getMonth() + 1, 1)
    return { start: toUTC(start), end: toUTC(end) }
  }

  // all time
  return { start: '2000-01-01T00:00:00Z', end: toUTC(now) }
}

export function useUsage(period: UsagePeriod = 'today') {
  const [usage, setUsage] = useState<UsageSummary | null>(null)
  const [series, setSeries] = useState<UsageSeries | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>
    let cancelled = false

    async function load() {
      try {
        const { start, end } = getRange(period)
        const bucket = bucketForPeriod(period)
        const tz = browserTimeZone()
        const [usageResult, seriesResult] = await Promise.all([
          fetchUsage(start, end),
          fetchUsageSeries(start, end, bucket, tz).catch(() => null),
        ])
        if (!cancelled) {
          setUsage(usageResult)
          setSeries(seriesResult)
        }
      } catch {}
      if (!cancelled) setLoading(false)
    }

    setLoading(true)
    setSeries(null)
    load()
    interval = setInterval(load, 30000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [period])

  return { usage, series, loading }
}
