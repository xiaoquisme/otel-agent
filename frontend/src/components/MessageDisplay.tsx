import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import type { StructuredMessage, MessageMetadata } from '../api/types'
import ToolCallBlock from './ToolCallBlock'
import ReasoningBlock from './ReasoningBlock'

interface MessageDisplayProps {
  messages: StructuredMessage[]
  metadata: MessageMetadata | null
}

function MessageBubble({ message }: { message: StructuredMessage }) {
  const roleStyles: Record<string, { bg: string; border: string; text: string; label: string }> = {
    system: { bg: 'var(--color-bg-elevated)', border: 'var(--color-border-default)', text: 'var(--color-text-secondary)', label: 'system' },
    user: { bg: 'var(--color-accent-blue-muted)', border: 'var(--color-accent-blue)', text: 'var(--color-accent-blue)', label: 'user' },
    assistant: { bg: 'var(--color-accent-green-muted)', border: 'var(--color-accent-green)', text: 'var(--color-accent-green)', label: 'assistant' },
    tool: { bg: 'var(--color-accent-yellow-muted)', border: 'var(--color-accent-yellow)', text: 'var(--color-accent-yellow)', label: 'tool' },
  }

  const role = roleStyles[message.role] || roleStyles.assistant
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content || '')
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard API not available
    }
  }

  return (
    <div style={{
      borderRadius: 'var(--radius-lg)',
      border: `1px solid ${role.border}`,
      background: role.bg,
      padding: 'var(--space-4)',
      marginBottom: 'var(--space-3)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-2)' }}>
        <span style={{
          fontSize: 'var(--text-xs)',
          fontFamily: 'var(--font-mono)',
          opacity: 0.7,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          color: role.text,
        }}>
          {role.label}
        </span>
        <button
          onClick={handleCopy}
          style={{
            marginLeft: 'auto',
            background: 'transparent',
            border: 'none',
            color: 'var(--color-text-secondary)',
            cursor: 'pointer',
            fontSize: 'var(--text-xs)',
            padding: '2px 4px',
          }}
        >
          {copied ? '✓ Copied' : 'Copy'}
        </button>
      </div>

      {message.reasoning_content && (
        <ReasoningBlock content={message.reasoning_content} />
      )}

      {message.content && (
        <div style={{ color: 'var(--color-text-primary)', lineHeight: 'var(--leading-relaxed)' }}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
          >
            {message.content}
          </ReactMarkdown>
        </div>
      )}

      {!message.content && !message.reasoning_content && (
        <div style={{ color: 'var(--color-text-secondary)', fontStyle: 'italic', fontSize: 'var(--text-sm)' }}>(empty)</div>
      )}

      {message.tool_calls && message.tool_calls.length > 0 && (
        <div style={{ marginTop: 'var(--space-3)', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          {message.tool_calls.map((tc, i) => (
            <ToolCallBlock key={i} id={tc.id} name={tc.name} arguments={tc.arguments} />
          ))}
        </div>
      )}
    </div>
  )
}

function MetadataBar({ metadata }: { metadata: MessageMetadata }) {
  if (!metadata) return null
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', marginBottom: 'var(--space-4)', fontSize: 'var(--text-xs)' }}>
      {metadata.model && (
        <span style={{ padding: 'var(--space-1) var(--space-2)', borderRadius: 'var(--radius-sm)', background: 'var(--color-bg-overlay)', color: 'var(--color-accent-blue)', fontFamily: 'var(--font-mono)' }}>
          {metadata.model}
        </span>
      )}
      {metadata.finish_reason && (
        <span style={{ padding: 'var(--space-1) var(--space-2)', borderRadius: 'var(--radius-sm)', background: 'var(--color-bg-overlay)', color: 'var(--color-text-secondary)' }}>
          {metadata.finish_reason}
        </span>
      )}
      {metadata.usage && (
        <span style={{ padding: 'var(--space-1) var(--space-2)', borderRadius: 'var(--radius-sm)', background: 'var(--color-bg-overlay)', color: 'var(--color-text-secondary)' }}>
          {metadata.usage.input_tokens ?? '?'} in / {metadata.usage.output_tokens ?? '?'} out
        </span>
      )}
    </div>
  )
}

import { useState } from 'react'

export default function MessageDisplay({ messages, metadata }: MessageDisplayProps) {
  if (!messages || messages.length === 0) {
    return (
      <div style={{ color: 'var(--color-text-secondary)', fontStyle: 'italic', fontSize: 'var(--text-sm)', padding: 'var(--space-4) 0' }}>
        No parsed messages available for this request.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
      {metadata && <MetadataBar metadata={metadata} />}
      {messages.map((msg, i) => (
        <MessageBubble key={i} message={msg} />
      ))}
    </div>
  )
}
