import { useRef, useEffect } from 'react'
import { Chart, registerables } from 'chart.js'
import type { RequestItem } from '../api/types'

Chart.register(...registerables)

interface LatencyChartProps {
  requests: RequestItem[]
}

export default function LatencyChart({ requests }: LatencyChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const chartRef = useRef<Chart | null>(null)

  useEffect(() => {
    if (!canvasRef.current) return

    const ctx = canvasRef.current.getContext('2d')
    if (!ctx) return

    chartRef.current = new Chart(ctx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          label: 'Latency (ms)',
          data: [],
          borderColor: 'var(--color-accent-blue)',
          backgroundColor: 'rgba(88, 166, 255, 0.1)',
          fill: true,
          tension: 0.3,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { display: false },
          y: {
            grid: { color: 'var(--color-border-muted)' },
            ticks: { color: 'var(--color-text-secondary)' },
          },
        },
      },
    })

    return () => { chartRef.current?.destroy() }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !requests.length) return

    const last = requests[requests.length - 1]
    const urlStr = typeof last.url === 'string' ? last.url : ''
    const label = last.method + ' ' + (urlStr.split('?')[0] || '')
    chart.data.labels!.push(label)
    chart.data.datasets[0].data.push(last.latency_ms || 0)

    if (chart.data.labels!.length > 50) {
      chart.data.labels!.shift()
      chart.data.datasets[0].data.shift()
    }
    chart.update()
  }, [requests])

  return (
    <div style={{ padding: 'var(--space-2) 0' }}>
      <canvas ref={canvasRef} style={{ maxHeight: '200px' }} />
    </div>
  )
}
