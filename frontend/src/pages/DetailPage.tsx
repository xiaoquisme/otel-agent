import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { fetchRequestDetail } from '../api/client'
import type { RequestDetail } from '../api/types'
import { Card, Tabs, TabList, Tab, TabPanel, Collapsible, CollapsibleTrigger, CollapsibleContent } from '../components/ui'
import MessageDisplay from '../components/MessageDisplay'
import CodeBlock from '../components/ui/CodeBlock'

function MetadataGrid({ detail }: { detail: RequestDetail }) {
  const items = [
    { label: 'Model', value: detail.model_name || detail.metadata?.model || '—', color: 'var(--color-accent-blue)' },
    { label: 'Finish Reason', value: detail.metadata?.finish_reason || '—', color: 'var(--color-accent-green)' },
    { label: 'Input Tokens', value: detail.metadata?.usage?.input_tokens?.toLocaleString() || '—', color: 'var(--color-text-primary)' },
    { label: 'Output Tokens', value: detail.metadata?.usage?.output_tokens?.toLocaleString() || '—', color: 'var(--color-text-primary)' },
    { label: 'Total Tokens', value: detail.metadata?.usage?.total_tokens?.toLocaleString() || '—', color: 'var(--color-text-primary)' },
    { label: 'Format', value: detail.metadata?.format || '—', color: 'var(--color-text-secondary)' },
  ]

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 'var(--space-3)' }}>
      {items.map((item) => (
        <div key={item.label} style={{ padding: 'var(--space-3)', background: 'var(--color-bg-elevated)', borderRadius: 'var(--radius-md)' }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginBottom: 'var(--space-1)' }}>
            {item.label}
          </div>
          <div style={{ fontSize: 'var(--text-sm)', color: item.color, fontWeight: 'var(--font-medium)' }}>
            {item.value}
          </div>
        </div>
      ))}
    </div>
  )
}

function HeadersBlock({ headers }: { headers: Record<string, string> | string | null }) {
  if (!headers) return <div style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-sm)' }}>(none)</div>

  let entries: [string, string][] = []
  if (typeof headers === 'string') {
    try {
      const parsed = JSON.parse(headers) as Record<string, string>
      entries = Object.entries(parsed)
    } catch {
      return <div style={{ fontSize: 'var(--text-sm)' }}>{headers}</div>
    }
  } else {
    entries = Object.entries(headers)
  }

  return (
    <div style={{ fontSize: 'var(--text-sm)' }}>
      {entries.map(([key, value]) => (
        <div key={key} style={{ display: 'flex', gap: 'var(--space-2)', padding: 'var(--space-1) 0', borderBottom: '1px solid var(--color-border-muted)' }}>
          <span style={{ color: 'var(--color-text-secondary)', minWidth: '200px' }}>{key}:</span>
          <span style={{ wordBreak: 'break-all' }}>{value}</span>
        </div>
      ))}
    </div>
  )
}

export default function DetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<RequestDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('formatted')

  useEffect(() => {
    if (!id) return
    setLoading(true)
    fetchRequestDetail(Number(id))
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false))
  }, [id])

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        navigate('/')
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [navigate])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 'var(--space-12)', color: 'var(--color-text-secondary)' }}>
        Loading...
      </div>
    )
  }

  if (!detail) {
    return (
      <div style={{ textAlign: 'center', padding: 'var(--space-12)', color: 'var(--color-text-secondary)' }}>
        Request not found
      </div>
    )
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
      {/* Back button */}
      <button
        onClick={() => navigate('/')}
        style={{
          background: 'none',
          border: 'none',
          color: 'var(--color-accent-blue)',
          cursor: 'pointer',
          fontSize: 'var(--text-sm)',
          marginBottom: 'var(--space-4)',
          padding: 0,
        }}
      >
        ← Back to list
      </button>

      {/* Request Header */}
      <Card padding="lg" style={{ marginBottom: 'var(--space-4)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
          <span
            style={{
              fontWeight: 'var(--font-bold)',
              fontSize: 'var(--text-lg)',
              padding: 'var(--space-1) var(--space-2)',
              borderRadius: 'var(--radius-sm)',
              background: detail.method === 'POST' ? 'var(--color-accent-purple-muted)' : 'var(--color-accent-green-muted)',
              color: detail.method === 'POST' ? 'var(--color-accent-purple)' : 'var(--color-accent-green)',
            }}
          >
            {detail.method}
          </span>
          <span style={{ fontSize: 'var(--text-base)', wordBreak: 'break-all' }}>
            {detail.url}
          </span>
        </div>

        <div style={{ display: 'flex', gap: 'var(--space-4)', fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
          <span>Status: <strong style={{ color: 'var(--color-text-primary)' }}>{detail.response_status}</strong></span>
          <span>Latency: <strong style={{ color: 'var(--color-text-primary)' }}>{detail.latency_ms?.toFixed(0) ?? 0}ms</strong></span>
        </div>
      </Card>

      {/* Metadata */}
      <Card padding="md" style={{ marginBottom: 'var(--space-4)' }}>
        <MetadataGrid detail={detail} />
      </Card>

      {/* Tabs for content */}
      <Tabs value={activeTab} onChange={setActiveTab}>
        <TabList>
          <Tab value="formatted">Formatted</Tab>
          <Tab value="raw">Raw</Tab>
          <Tab value="headers">Headers</Tab>
        </TabList>

        <TabPanel value="formatted">
          {/* Conversation */}
          <Collapsible defaultOpen>
            <CollapsibleTrigger>
              <span style={{ fontWeight: 'var(--font-semibold)' }}>Conversation</span>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <MessageDisplay
                messages={detail.messages ?? []}
                metadata={detail.metadata}
              />
            </CollapsibleContent>
          </Collapsible>
        </TabPanel>

        <TabPanel value="raw">
          {/* Request Body */}
          <Collapsible defaultOpen>
            <CollapsibleTrigger>
              <span style={{ fontWeight: 'var(--font-semibold)' }}>Request Body</span>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <CodeBlock data={detail.request_body || '(empty)'} />
            </CollapsibleContent>
          </Collapsible>

          {/* Response Body */}
          <Collapsible defaultOpen>
            <CollapsibleTrigger>
              <span style={{ fontWeight: 'var(--font-semibold)' }}>Response Body</span>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <CodeBlock data={detail.response_body || '(empty)'} />
            </CollapsibleContent>
          </Collapsible>
        </TabPanel>

        <TabPanel value="headers">
          {/* Request Headers */}
          <Collapsible defaultOpen>
            <CollapsibleTrigger>
              <span style={{ fontWeight: 'var(--font-semibold)' }}>Request Headers</span>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <HeadersBlock headers={detail.request_headers} />
            </CollapsibleContent>
          </Collapsible>

          {/* Response Headers */}
          <Collapsible defaultOpen>
            <CollapsibleTrigger>
              <span style={{ fontWeight: 'var(--font-semibold)' }}>Response Headers</span>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <HeadersBlock headers={detail.response_headers} />
            </CollapsibleContent>
          </Collapsible>
        </TabPanel>
      </Tabs>
    </div>
  )
}
