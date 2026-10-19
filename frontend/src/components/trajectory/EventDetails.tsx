import { useState, type KeyboardEvent } from 'react'
import type { RequestDetail } from '../../api/types'
import { CodeBlock } from '../ui'
import MessageDisplay from '../MessageDisplay'
import ReasoningBlock from '../ReasoningBlock'
import type { TrajectoryCell } from './buildTrajectoryCells'
import './trajectory.css'

interface EventDetailsProps {
  detail: RequestDetail
  cell: TrajectoryCell | null
}

const TABS = [
  { id: 'summary', label: 'Summary' },
  { id: 'payload', label: 'Payload' },
  { id: 'result', label: 'Result' },
  { id: 'timing', label: 'Timing' },
] as const

type DetailTab = (typeof TABS)[number]['id']

function tokenText(value: number | null | undefined): string {
  return value == null ? '—' : value.toLocaleString()
}

function Overview({ rows }: { rows: { label: string; value: string }[] }) {
  return (
    <dl className="dsh-overview">
      {rows.map((row) => (
        <div key={row.label}>
          <dt>{row.label}</dt>
          <dd title={row.value}>{row.value}</dd>
        </div>
      ))}
    </dl>
  )
}

export default function EventDetails({ detail, cell }: EventDetailsProps) {
  const [active, setActive] = useState<DetailTab>('summary')

  if (!cell) {
    return (
      <aside className="dsh-details" aria-label="Event details">
        <div className="dsh-details-empty">Select a step</div>
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

  const usage = detail.metadata?.usage
  const title = cell.toolCall?.name ?? cell.kind

  const onTabKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = TABS.findIndex((tab) => tab.id === active)
    let next = index
    if (event.key === 'ArrowRight') next = (index + 1) % TABS.length
    else if (event.key === 'ArrowLeft') next = (index - 1 + TABS.length) % TABS.length
    else return
    event.preventDefault()
    const id = TABS[next].id
    setActive(id)
    event.currentTarget.querySelector<HTMLButtonElement>(`#dsh-tab-${id}`)?.focus()
  }

  return (
    <aside className="dsh-details" aria-label="Event details">
      <div className="dsh-details-header">
        <div className="dsh-details-title">
          <span className="dsh-details-name">{title}</span>
          <span className="dsh-details-location">Step {cell.index}</span>
        </div>
      </div>
      <div className="dsh-tabs" role="tablist" aria-label="Event detail sections" onKeyDown={onTabKey}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            id={`dsh-tab-${tab.id}`}
            type="button"
            role="tab"
            className="dsh-tab"
            aria-selected={active === tab.id}
            aria-controls={`dsh-panel-${tab.id}`}
            tabIndex={active === tab.id ? 0 : -1}
            onClick={() => setActive(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div
        id={`dsh-panel-${active}`}
        role="tabpanel"
        className="dsh-detail-body"
        aria-labelledby={`dsh-tab-${active}`}
      >
        {active === 'summary' && (
          <Overview
            rows={[
              { label: 'Role', value: cell.message.role },
              { label: 'Model', value: detail.model_name || detail.metadata?.model || '—' },
              { label: 'Finish', value: detail.metadata?.finish_reason || '—' },
              { label: 'Input', value: tokenText(usage?.input_tokens) },
              { label: 'Output', value: tokenText(usage?.output_tokens) },
              { label: 'Tokens', value: tokenText(usage?.total_tokens) },
            ]}
          />
        )}
        {active === 'payload' && (
          <div className="dsh-detail-pad">
            {cell.kind === 'REASONING' && cell.message.reasoning_content ? (
              <ReasoningBlock content={cell.message.reasoning_content} />
            ) : (
              <CodeBlock data={payload} title={cell.toolCall ? cell.toolCall.name : cell.kind} maxHeight="none" />
            )}
          </div>
        )}
        {active === 'result' && (
          <div className="dsh-detail-pad">
            {result ? (
              <MessageDisplay messages={[cell.message]} metadata={detail.metadata} />
            ) : (
              <div className="dsh-muted">No result on this step</div>
            )}
          </div>
        )}
        {active === 'timing' && (
          <Overview
            rows={[
              { label: 'Latency', value: `${detail.latency_ms?.toFixed(0) ?? '—'} ms` },
              { label: 'Timestamp', value: detail.timestamp || '—' },
            ]}
          />
        )}
      </div>
    </aside>
  )
}
