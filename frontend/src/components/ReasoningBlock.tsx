import { useState } from 'react'

interface ReasoningBlockProps {
  content: string
}

export default function ReasoningBlock({ content }: ReasoningBlockProps) {
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)

  if (!content) return null

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard API not available
    }
  }

  return (
    <div style={{ borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border-default)', background: 'var(--color-bg-base)', marginBottom: 'var(--space-3)', overflow: 'hidden' }}>
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          padding: 'var(--space-2) var(--space-3)',
          textAlign: 'left',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          transition: 'background var(--transition-fast)',
        }}
        onMouseEnter={(e) => e.currentTarget.style.background = 'var(--color-bg-surface)'}
        onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
      >
        <span style={{ color: 'var(--color-accent-purple)', fontSize: 'var(--text-xs)' }}>💭</span>
        <span style={{ color: 'var(--color-accent-purple)', fontSize: 'var(--text-sm)' }}>Reasoning</span>
        <span style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)', marginLeft: 'auto' }}>
          {expanded ? '▾' : '▸'}
        </span>
      </button>
      {expanded && (
        <div style={{ padding: '0 var(--space-3) var(--space-3)', borderTop: '1px solid var(--color-border-muted)' }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--space-2)' }}>
            <button
              onClick={handleCopy}
              style={{
                background: 'var(--color-bg-overlay)',
                border: '1px solid var(--color-border-default)',
                color: 'var(--color-text-secondary)',
                padding: '2px 6px',
                borderRadius: 'var(--radius-sm)',
                fontSize: 'var(--text-xs)',
                cursor: 'pointer',
              }}
            >
              {copied ? '✓ Copied' : 'Copy'}
            </button>
          </div>
          <div style={{
            fontSize: 'var(--text-sm)',
            color: 'var(--color-text-secondary)',
            marginTop: 'var(--space-2)',
            whiteSpace: 'pre-wrap',
            lineHeight: 'var(--leading-relaxed)',
          }}>
            {content}
          </div>
        </div>
      )}
    </div>
  )
}
