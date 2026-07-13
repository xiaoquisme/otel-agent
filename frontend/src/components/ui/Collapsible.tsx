import {
  useState,
  useCallback,
  createContext,
  useContext,
  useMemo,
  type ReactNode,
  type ButtonHTMLAttributes,
  type CSSProperties,
} from 'react'

// ─── Context ────────────────────────────────────────────────────────────────

interface CollapsibleContextValue {
  open: boolean
  onToggle: () => void
  disabled: boolean
  contentId: string
}

const CollapsibleContext = createContext<CollapsibleContextValue | null>(null)

function useCollapsibleContext(componentName: string): CollapsibleContextValue {
  const ctx = useContext(CollapsibleContext)
  if (!ctx) {
    throw new Error(
      `<${componentName}> must be used within a <Collapsible> root.`,
    )
  }
  return ctx
}

// ─── Root ───────────────────────────────────────────────────────────────────

let idCounter = 0
function generateId(prefix = 'collapsible') {
  return `${prefix}-${++idCounter}`
}

export interface CollapsibleProps {
  /** Controlled open state. If omitted, the component manages its own state. */
  open?: boolean
  /** Initial open state for the uncontrolled variant. */
  defaultOpen?: boolean
  /** Fires when the open state changes. */
  onOpenChange?: (open: boolean) => void
  /** Disables toggling. */
  disabled?: boolean
  /** Children — must include a <CollapsibleTrigger> and a <CollapsibleContent>. */
  children: ReactNode
  /** Additional class name on the root element. */
  className?: string
  /** Additional styles on the root element. */
  style?: CSSProperties
}

export function Collapsible({
  open: controlledOpen,
  defaultOpen = false,
  onOpenChange,
  disabled = false,
  children,
  className,
  style,
}: CollapsibleProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen)

  const isControlled = controlledOpen !== undefined
  const open = isControlled ? controlledOpen : uncontrolledOpen

  const contentId = useMemo(() => generateId('collapsible-content'), [])

  const onToggle = useCallback(() => {
    if (disabled) return
    const next = !open
    if (!isControlled) {
      setUncontrolledOpen(next)
    }
    onOpenChange?.(next)
  }, [open, disabled, isControlled, onOpenChange])

  const ctx = useMemo<CollapsibleContextValue>(
    () => ({ open, onToggle, disabled, contentId }),
    [open, onToggle, disabled, contentId],
  )

  return (
    <CollapsibleContext.Provider value={ctx}>
      <div
        className={className}
        style={{
          '--collapsible-duration': 'var(--transition-slow, 300ms)',
          ...style,
        } as CSSProperties}
      >
        {children}
      </div>
    </CollapsibleContext.Provider>
  )
}

// ─── Trigger ────────────────────────────────────────────────────────────────

export interface CollapsibleTriggerProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Render as a different element (e.g. a div wrapper). Defaults to <button>. */
  asChild?: boolean
}

export function CollapsibleTrigger({
  children,
  className,
  disabled: buttonDisabled,
  ...rest
}: CollapsibleTriggerProps) {
  const { open, onToggle, disabled: ctxDisabled } = useCollapsibleContext('CollapsibleTrigger')
  const disabled = ctxDisabled || buttonDisabled

  return (
    <button
      type="button"
      aria-expanded={open}
      disabled={disabled}
      onClick={onToggle}
      className={className}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-2, 8px)',
        width: '100%',
        padding: 'var(--space-2, 8px) var(--space-3, 12px)',
        fontSize: 'var(--text-sm, 13px)',
        fontFamily: 'var(--font-sans)',
        fontWeight: 'var(--font-medium, 500)',
        color: 'var(--color-text-primary, #e1e4e8)',
        background: 'transparent',
        border: 'none',
        borderRadius: 'var(--radius-md, 6px)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        textAlign: 'left',
        transition: 'background var(--transition-fast, 100ms ease)',
        ...rest.style,
      }}
      onMouseEnter={(e) => {
        if (!disabled) {
          ;(e.currentTarget as HTMLElement).style.background =
            'var(--color-bg-muted, #30363d)'
        }
        rest.onMouseEnter?.(e)
      }}
      onMouseLeave={(e) => {
        ;(e.currentTarget as HTMLElement).style.background = 'transparent'
        rest.onMouseLeave?.(e)
      }}
      {...rest}
    >
      {children}
      <span
        aria-hidden
        style={{
          marginLeft: 'auto',
          transition: 'transform var(--transition-base, 200ms ease)',
          transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
          color: 'var(--color-text-muted, #6e7681)',
          fontSize: 'var(--text-xs, 11px)',
        }}
      >
        ›
      </span>
    </button>
  )
}

// ─── Content ────────────────────────────────────────────────────────────────

export interface CollapsibleContentProps {
  children: ReactNode
  className?: string
  style?: CSSProperties
}

export function CollapsibleContent({
  children,
  className,
  style,
}: CollapsibleContentProps) {
  const { open, contentId } = useCollapsibleContext('CollapsibleContent')

  return (
    <div
      id={contentId}
      role="region"
      className={className}
      style={{
        display: 'grid',
        gridTemplateRows: open ? '1fr' : '0fr',
        transition:
          'grid-template-rows var(--collapsible-duration, var(--transition-slow, 300ms)) ease',
        ...style,
      }}
    >
      <div style={{ overflow: 'hidden', minHeight: 0 }}>
        {children}
      </div>
    </div>
  )
}

// ─── Compound export & convenience alias ─────────────────────────────────────

export const CollapsibleRoot = Collapsible
