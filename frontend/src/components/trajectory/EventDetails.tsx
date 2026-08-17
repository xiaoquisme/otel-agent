import type { RequestDetail } from '../../api/types'
import { Tabs, TabList, Tab, TabPanel, CodeBlock } from '../ui'
import MessageDisplay from '../MessageDisplay'
import ReasoningBlock from '../ReasoningBlock'
import type { TrajectoryCell } from './buildTrajectoryCells'

interface EventDetailsProps {
  detail: RequestDetail
  cell: TrajectoryCell | null
}

export default function EventDetails({ detail, cell }: EventDetailsProps) {
  if (!cell) {
    return (
      <aside
        aria-label="Event details"
        style={{
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--color-text-muted)',
          fontSize: 'var(--text-sm)',
          padding: 'var(--space-4)',
        }}
      >
        Select a step
      </aside>
    )
  }

  let payload: unknown = cell.message.content
  if (cell.toolCall) {
    try {
      payload = JSON.parse(cell.toolCall.arguments)
    } catch {
      payload = cell.toolCall.arguments
    }
  } else if (cell.kind === 'REASONING') {
    payload = cell.message.reasoning_content
  }

  const result = cell.kind === 'TOOL' && !cell.toolCall
    ? cell.message.content
    : cell.kind === 'ASSISTANT'
      ? cell.message.content
      : cell.toolCall
        ? null
        : cell.message.content

  return (
    <aside
      aria-label="Event details"
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
        background: 'var(--color-bg-surface)',
      }}
    >
      <div
        style={{
          padding: 'var(--space-3) var(--space-4)',
          borderBottom: '1px solid var(--color-border-default)',
          fontSize: 'var(--text-sm)',
          flexShrink: 0,
        }}
      >
        <strong>{cell.kind}</strong>
        <span style={{ color: 'var(--color-text-secondary)', marginLeft: 'var(--space-2)' }}>
          Step {cell.index}
          {cell.toolCall ? ` · ${cell.toolCall.name}` : ''}
        </span>
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: 'var(--space-3)' }}>
        <Tabs defaultValue="summary" size="sm">
          <TabList>
            <Tab value="summary">Summary</Tab>
            <Tab value="payload">Payload</Tab>
            <Tab value="result">Result</Tab>
            <Tab value="timing">Timing</Tab>
          </TabList>
          <TabPanel value="summary">
            <dl style={{ fontSize: 'var(--text-sm)', display: 'grid', gridTemplateColumns: '120px 1fr', gap: 'var(--space-2)' }}>
              <dt style={{ color: 'var(--color-text-secondary)' }}>Role</dt>
              <dd style={{ margin: 0 }}>{cell.message.role}</dd>
              <dt style={{ color: 'var(--color-text-secondary)' }}>Model</dt>
              <dd style={{ margin: 0 }}>{detail.model_name || detail.metadata?.model || '—'}</dd>
              <dt style={{ color: 'var(--color-text-secondary)' }}>Finish</dt>
              <dd style={{ margin: 0 }}>{detail.metadata?.finish_reason || '—'}</dd>
              <dt style={{ color: 'var(--color-text-secondary)' }}>Tokens</dt>
              <dd style={{ margin: 0 }}>
                {detail.metadata?.usage?.total_tokens?.toLocaleString() ?? '—'}
              </dd>
            </dl>
          </TabPanel>
          <TabPanel value="payload">
            {cell.kind === 'REASONING' && cell.message.reasoning_content ? (
              <ReasoningBlock content={cell.message.reasoning_content} />
            ) : (
              <CodeBlock data={payload} title={cell.toolCall ? cell.toolCall.name : cell.kind} />
            )}
          </TabPanel>
          <TabPanel value="result">
            {result ? (
              <MessageDisplay messages={[cell.message]} metadata={detail.metadata} />
            ) : (
              <div style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>No result on this step</div>
            )}
          </TabPanel>
          <TabPanel value="timing">
            <dl style={{ fontSize: 'var(--text-sm)', display: 'grid', gridTemplateColumns: '120px 1fr', gap: 'var(--space-2)' }}>
              <dt style={{ color: 'var(--color-text-secondary)' }}>Latency</dt>
              <dd style={{ margin: 0 }}>{detail.latency_ms?.toFixed(0) ?? '—'} ms</dd>
              <dt style={{ color: 'var(--color-text-secondary)' }}>Timestamp</dt>
              <dd style={{ margin: 0 }}>{detail.timestamp}</dd>
            </dl>
          </TabPanel>
        </Tabs>
      </div>
    </aside>
  )
}
