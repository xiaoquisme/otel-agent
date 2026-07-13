import { useState } from 'react'

interface ToolCallBlockProps {
  name: string
  arguments: string
}

function formatArguments(args: string): string {
  try {
    const parsed = JSON.parse(args)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return args
  }
}

export default function ToolCallBlock({ name, arguments: args }: ToolCallBlockProps) {
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(formatArguments(args))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard API not available
    }
  }

  return (
    <div style={{ borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border-default)', background: 'var(--color-bg-base)', overflow: 'hidden' }}>
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
        <span style={{ color: 'var(--color-accent-yellow)', fontSize: 'var(--text-xs)' }}>⚡</span>
        <span style={{ color: 'var(--color-text-primary)', fontSize: 'var(--text-sm)', fontFamily: 'var(--font-mono)' }}>{name}</span>
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
          <pre style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--color-text-primary)',
            overflowX: 'auto',
            marginTop: 'var(--space-2)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
            fontFamily: 'var(--font-mono)',
          }}>
            {formatArguments(args)}
          </pre>
        </div>
      )}
    </div>
  )
}
