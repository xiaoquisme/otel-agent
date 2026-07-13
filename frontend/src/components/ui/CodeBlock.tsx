import { useState, useCallback, useMemo } from 'react'

interface CodeBlockProps {
  /** JSON data to render (object, string, or any serializable value) */
  data: unknown
  /** Optional title shown in the header */
  title?: string
  /** Whether to show line numbers (default: true) */
  showLineNumbers?: boolean
  /** Whether to show the copy button (default: true) */
  showCopyButton?: boolean
  /** Optional max height before scrolling (CSS value) */
  maxHeight?: string
  /** Additional className to apply to the root element */
  className?: string
}

/**
 * Escape HTML special characters to prevent XSS in dangerouslySetInnerHTML.
 */
function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * Recursively highlight a parsed JSON value, returning HTML
 * with syntax-colouring spans that match globals.css classes.
 */
function highlightJson(obj: unknown, indent: number = 0): string {
  const pad = '  '.repeat(indent)

  if (obj === null) return `${pad}<span class="json-null">null</span>`
  if (typeof obj === 'boolean')
    return `${pad}<span class="json-boolean">${obj}</span>`
  if (typeof obj === 'number')
    return `${pad}<span class="json-number">${obj}</span>`
  if (typeof obj === 'string') {
    const escaped = escapeHtml(obj)
    return `${pad}<span class="json-string">"${escaped}"</span>`
  }

  if (Array.isArray(obj)) {
    if (obj.length === 0) return `${pad}[]`
    const items = obj.map((v) => highlightJson(v, indent + 1))
    return `${pad}[\n${items.join(',\n')}\n${pad}]`
  }

  if (typeof obj === 'object') {
    const keys = Object.keys(obj as Record<string, unknown>)
    if (keys.length === 0) return `${pad}{}`
    const entries = keys.map((k) => {
      const escaped = escapeHtml(k)
      return `${pad}  <span class="json-key">"${escaped}"</span>: ${highlightJson((obj as Record<string, unknown>)[k], indent + 1).trim()}`
    })
    return `${pad}{\n${entries.join(',\n')}\n${pad}}`
  }

  return pad + String(obj)
}

/**
 * Format the raw value for the clipboard (no HTML, just pretty-printed text).
 */
function formatPlainText(obj: unknown): string {
  if (typeof obj === 'string') {
    try {
      return JSON.stringify(JSON.parse(obj), null, 2)
    } catch {
      return obj
    }
  }
  return JSON.stringify(obj, null, 2)
}

export default function CodeBlock({
  data,
  title,
  showLineNumbers = true,
  showCopyButton = true,
  maxHeight = '600px',
  className = '',
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false)

  // Memoize the parsed + highlighted result so it only recalculates on data change
  const { highlightedHtml, plainText } = useMemo(() => {
    let parsed: unknown = data
    if (typeof data === 'string') {
      try {
        parsed = JSON.parse(data)
      } catch {
        // Keep as-is — render as escaped text
      }
    }

    const html = highlightJson(parsed, 0)
    const plain = formatPlainText(data)

    return {
      highlightedHtml: html,
      plainText: plain,
    }
  }, [data])

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(plainText)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement('textarea')
      textarea.value = plainText
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }, [plainText])

  return (
    <div
      className={`relative overflow-hidden rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] ${className}`}
    >
      {/* Header bar */}
      {(title || showCopyButton) && (
        <div className="flex items-center justify-between border-b border-[var(--color-border-muted)] bg-[var(--color-bg-elevated)] px-3 py-1.5">
          {title ? (
            <span
              className="truncate text-xs font-medium text-[var(--color-text-secondary)]"
              style={{ fontFamily: 'var(--font-mono)' }}
            >
              {title}
            </span>
          ) : (
            <span />
          )}
          {showCopyButton && (
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 rounded px-2 py-0.5 text-xs text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-bg-muted)] hover:text-[var(--color-text-secondary)]"
              style={{ fontFamily: 'var(--font-sans)' }}
              title="Copy to clipboard"
            >
              {copied ? (
                <>
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 16 16"
                    fill="currentColor"
                  >
                    <path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 0 1 1.06-1.06L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z" />
                  </svg>
                  <span>Copied</span>
                </>
              ) : (
                <>
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 16 16"
                    fill="currentColor"
                  >
                    <path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25v-7.5Z" />
                    <path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25v-7.5Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25h-7.5Z" />
                  </svg>
                  <span>Copy</span>
                </>
              )}
            </button>
          )}
        </div>
      )}

      {/* Code content */}
      <div
        className="overflow-auto"
        style={{ maxHeight }}
      >
        <table
          className="border-collapse"
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 'var(--text-sm)',
            lineHeight: 'var(--leading-relaxed)',
            width: '100%',
          }}
        >
          <tbody>
            {highlightedHtml.split('\n').map((line, i) => (
              <tr key={i} className="group">
                {showLineNumbers && (
                  <td
                    className="select-none border-r border-[var(--color-border-muted)] px-3 text-right align-top text-[var(--color-text-muted)]"
                    style={{
                      width: '1%',
                      whiteSpace: 'nowrap',
                      fontSize: 'var(--text-xs)',
                    }}
                  >
                    {i + 1}
                  </td>
                )}
                <td
                  className="whitespace-pre px-4 text-[var(--color-text-primary)]"
                  dangerouslySetInnerHTML={{ __html: line || ' ' }}
                />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
