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
          borderColor: '#58a6ff',
          backgroundColor: 'rgba(88,166,255,0.1)',
          fill: true,
          tension: 0.3,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { display: false },
          y: { grid: { color: '#21262d' }, ticks: { color: '#8b949e' } },
        },
      },
    })

    return () => { chartRef.current?.destroy() }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !requests.length) return

    const last = requests[requests.length - 1]
    const label = last.method + ' ' + (last.url?.split('?')[0] || '')
    chart.data.labels!.push(label)
    chart.data.datasets[0].data.push(last.latency_ms || 0)

    if (chart.data.labels!.length > 50) {
      chart.data.labels!.shift()
      chart.data.datasets[0].data.shift()
    }
    chart.update()
  }, [requests])

  return (
    <div className="px-6 py-2">
      <canvas ref={canvasRef} className="max-h-[200px]" />
    </div>
  )
}
