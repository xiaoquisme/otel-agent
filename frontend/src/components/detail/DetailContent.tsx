import { useState } from 'react'
import type { RequestDetail } from '../../api/types'
import { Tabs, TabList, Tab, TabPanel, Collapsible, CollapsibleTrigger, CollapsibleContent } from '../ui'
import MessageDisplay from '../MessageDisplay'
import CodeBlock from '../ui/CodeBlock'

interface DetailContentProps {
  detail: RequestDetail
  compact?: boolean
}

function MetadataGrid({ detail, compact }: { detail: RequestDetail; compact?: boolean }) {
  const items = [
    { label: 'Model', value: detail.model_name || detail.metadata?.model || '—', color: 'var(--color-accent-blue)' },
    { label: 'Finish Reason', value: detail.metadata?.finish_reason || '—', color: 'var(--color-accent-green)' },
    { label: 'Input Tokens', value: detail.metadata?.usage?.input_tokens?.toLocaleString() || '—', color: 'var(--color-text-primary)' },
    { label: 'Output Tokens', value: detail.metadata?.usage?.output_tokens?.toLocaleString() || '—', color: 'var(--color-text-primary)' },
    { label: 'Total Tokens', value: detail.metadata?.usage?.total_tokens?.toLocaleString() || '—', color: 'var(--color-text-primary)' },
    { label: 'Format', value: detail.metadata?.format || '—', color: 'var(--color-text-secondary)' },
  ]

  if (compact) {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-2)' }}>
        {items.slice(0, 3).map((item) => (
          <div key={item.label} style={{ fontSize: 'var(--text-xs)' }}>
            <div style={{ color: 'var(--color-text-muted)', marginBottom: '1px' }}>{item.label}</div>
            <div style={{ color: item.color, fontFamily: 'var(--font-mono)' }}>{item.value}</div>
          </div>
        ))}
      </div>
    )
  }

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

export default function DetailContent({ detail, compact = false }: DetailContentProps) {
  const [activeTab, setActiveTab] = useState('formatted')

  return (
    <>
      {/* Metadata */}
      <div style={{ padding: compact ? 'var(--space-2) var(--space-3)' : undefined, borderBottom: '1px solid var(--color-border-muted)', flexShrink: 0 }}>
        <MetadataGrid detail={detail} compact={compact} />
      </div>

      {/* Usage metrics (compact mode only) */}
      {compact && detail.metadata?.usage && (
        <div
          style={{
            display: 'flex',
            gap: 'var(--space-3)',
            padding: 'var(--space-2) var(--space-3)',
            borderBottom: '1px solid var(--color-border-muted)',
            fontSize: 'var(--text-xs)',
            fontFamily: 'var(--font-mono)',
            flexShrink: 0,
          }}
        >
          <span style={{ color: 'var(--color-text-muted)' }}>
            in: <span style={{ color: 'var(--color-text-primary)' }}>{detail.metadata.usage.input_tokens ?? '—'}</span>
          </span>
          <span style={{ color: 'var(--color-text-muted)' }}>
            out: <span style={{ color: 'var(--color-text-primary)' }}>{detail.metadata.usage.output_tokens ?? '—'}</span>
          </span>
          {detail.metadata.finish_reason && (
            <span style={{ color: 'var(--color-text-muted)' }}>
              stop: <span style={{ color: 'var(--color-text-primary)' }}>{detail.metadata.finish_reason}</span>
            </span>
          )}
        </div>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onChange={setActiveTab}>
        <TabList>
          <Tab value="formatted">Conversation</Tab>
          <Tab value="raw">Raw</Tab>
          <Tab value="headers">Headers</Tab>
        </TabList>

        <TabPanel value="formatted">
          <Collapsible defaultOpen>
            <CollapsibleTrigger>
              <span style={{ fontWeight: 'var(--font-semibold)' }}>Messages</span>
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
          <Collapsible defaultOpen>
            <CollapsibleTrigger>
              <span style={{ fontWeight: 'var(--font-semibold)' }}>Request Body</span>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <CodeBlock data={detail.request_body || '(empty)'} />
            </CollapsibleContent>
          </Collapsible>

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
          <Collapsible defaultOpen>
            <CollapsibleTrigger>
              <span style={{ fontWeight: 'var(--font-semibold)' }}>Request Headers</span>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <HeadersBlock headers={detail.request_headers} />
            </CollapsibleContent>
          </Collapsible>

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
    </>
  )
}
