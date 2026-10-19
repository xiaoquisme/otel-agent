import { useEffect, useRef } from 'react'
import { Chart, registerables } from 'chart.js'
import type { TooltipItem } from 'chart.js'
import type { UsageBucket, UsageSeries } from '../api/types'

Chart.register(...registerables)

const BUCKET_TITLES: Record<UsageBucket, string> = {
  hour: 'Hourly',
  day: 'Daily',
  week: 'Weekly',
  month: 'Monthly',
}

function cssVar(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

function formatNumber(n: number): string {
  if (!Number.isFinite(n)) return '0'
  const abs = Math.abs(n)
  if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return Math.round(n).toLocaleString()
}

function formatLabel(iso: string, bucket: UsageBucket): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  if (bucket === 'hour') return date.toLocaleTimeString(undefined, { hour: 'numeric' })
  if (bucket === 'month') return date.toLocaleDateString(undefined, { month: 'short', year: 'numeric' })
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function formatTitle(iso: string, bucket: UsageBucket): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  if (bucket === 'hour') {
    return date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric' })
  }
  if (bucket === 'week') {
    const label = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
    return `Week of ${label}`
  }
  if (bucket === 'month') return date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
  return date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
}

interface UsageChartProps {
  series: UsageSeries
}

export default function UsageChart({ series }: UsageChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const chartRef = useRef<Chart | null>(null)
  const seriesRef = useRef(series)
  seriesRef.current = series

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const text = cssVar('--color-text-secondary', '#656d76')
    const grid = cssVar('--color-border-muted', '#eaeef2')
    const input = cssVar('--color-accent-green', '#1a7f37')
    const output = cssVar('--color-accent-purple', '#8250df')
    const font = cssVar('--font-sans', 'sans-serif')

    chartRef.current = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [
          {
            label: 'Input',
            data: [],
            backgroundColor: input,
            stack: 'tokens',
            borderRadius: 2,
            maxBarThickness: 72,
          },
          {
            label: 'Output',
            data: [],
            backgroundColor: output,
            stack: 'tokens',
            borderRadius: 2,
            maxBarThickness: 72,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            position: 'top',
            align: 'end',
            labels: {
              color: text,
              boxWidth: 10,
              boxHeight: 10,
              font: { size: 11, family: font },
            },
          },
          tooltip: {
            callbacks: {
              title(items) {
                const index = items[0]?.dataIndex ?? 0
                const point = seriesRef.current.points[index]
                if (!point) return ''
                return formatTitle(point.bucket_start, seriesRef.current.bucket)
              },
              label(item: TooltipItem<'bar'>) {
                return `${item.dataset.label ?? ''}: ${formatNumber(Number(item.parsed.y) || 0)}`
              },
              afterBody(items) {
                const index = items[0]?.dataIndex ?? 0
                const point = seriesRef.current.points[index]
                if (!point) return ''
                const requests = point.request_count === 1
                  ? '1 request'
                  : `${formatNumber(point.request_count)} requests`
                return [`Total: ${formatNumber(point.total_tokens)}`, requests]
              },
            },
          },
        },
        scales: {
          x: {
            stacked: true,
            grid: { display: false },
            ticks: {
              color: text,
              maxRotation: 0,
              autoSkip: true,
              font: { size: 11, family: font },
            },
          },
          y: {
            stacked: true,
            beginAtZero: true,
            grid: { color: grid },
            ticks: {
              color: text,
              font: { size: 11, family: font },
              callback(value) {
                return formatNumber(Number(value) || 0)
              },
            },
          },
        },
      },
    })

    return () => {
      chartRef.current?.destroy()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.data.labels = series.points.map((point) => formatLabel(point.bucket_start, series.bucket))
    chart.data.datasets[0].data = series.points.map((point) => point.input_tokens)
    chart.data.datasets[1].data = series.points.map((point) => point.output_tokens)
    chart.update()
  }, [series])

  const total = series.points.reduce((sum, point) => sum + (point.total_tokens || 0), 0)
  const cadence = BUCKET_TITLES[series.bucket]
  const ariaLabel = `${cadence} token usage, ${formatNumber(total)} total tokens across ${series.points.length} buckets`

  return (
    <div
      role="img"
      aria-label={ariaLabel}
      style={{
        background: 'var(--color-bg-surface)',
        border: '1px solid var(--color-border-default)',
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-4)',
        marginBottom: 'var(--space-4)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
        <h3 style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', margin: 0 }}>
          Tokens over time
        </h3>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>{cadence}</span>
      </div>
      <div style={{ position: 'relative', height: '220px' }}>
        <canvas ref={canvasRef} />
      </div>
    </div>
  )
}
