import { createContext, useContext, useState, useCallback, useMemo, type ReactNode } from 'react'

// ── Types ──

export type TabsSize = 'sm' | 'md' | 'lg'

export interface TabsProps {
  /** Currently active tab key (controlled mode) */
  value?: string
  /** Default active tab key (uncontrolled mode) */
  defaultValue?: string
  /** Callback when the active tab changes */
  onChange?: (value: string) => void
  /** Size variant for all child tabs */
  size?: TabsSize
  /** Layout direction */
  orientation?: 'horizontal' | 'vertical'
  /** Additional class name for the root container */
  className?: string
  /** TabList and TabPanel children */
  children: ReactNode
}

export interface TabListProps {
  /** Tab elements */
  children: ReactNode
  /** Additional class name */
  className?: string
}

export interface TabProps {
  /** Unique key that identifies this tab */
  value: string
  /** Label text or content for the tab */
  children: ReactNode
  /** Whether the tab is disabled */
  disabled?: boolean
  /** Additional class name */
  className?: string
}

export interface TabPanelProps {
  /** Must match the corresponding Tab's value */
  value: string
  /** Panel content */
  children: ReactNode
  /** Additional class name */
  className?: string
}

// ── Context ──

interface TabsContextValue {
  activeTab: string
  setActiveTab: (value: string) => void
  size: TabsSize
  orientation: 'horizontal' | 'vertical'
}

const TabsContext = createContext<TabsContextValue | null>(null)

function useTabsContext(): TabsContextValue {
  const ctx = useContext(TabsContext)
  if (!ctx) throw new Error('Tabs compound components must be used within <Tabs>')
  return ctx
}

// ── Size maps ──

const tabSizeStyles: Record<TabsSize, { fontSize: string; paddingX: string; paddingY: string; gap: string }> = {
  sm: { fontSize: 'var(--text-xs)', paddingX: 'var(--space-2)', paddingY: 'var(--space-1)', gap: 'var(--space-1)' },
  md: { fontSize: 'var(--text-sm)', paddingX: 'var(--space-3)', paddingY: 'var(--space-2)', gap: 'var(--space-2)' },
  lg: { fontSize: 'var(--text-base)', paddingX: 'var(--space-4)', paddingY: 'var(--space-3)', gap: 'var(--space-3)' },
}

// ── Root ──

export default function Tabs({
  value,
  defaultValue,
  onChange,
  size = 'md',
  orientation = 'horizontal',
  className,
  children,
}: TabsProps) {
  const [internalValue, setInternalValue] = useState(defaultValue ?? '')
  const isControlled = value !== undefined
  const activeTab = isControlled ? value : internalValue

  const setActiveTab = useCallback(
    (next: string) => {
      if (!isControlled) setInternalValue(next)
      onChange?.(next)
    },
    [isControlled, onChange],
  )

  const ctx = useMemo<TabsContextValue>(
    () => ({ activeTab, setActiveTab, size, orientation }),
    [activeTab, setActiveTab, size, orientation],
  )

  const rootStyles: React.CSSProperties = {
    fontFamily: 'var(--font-sans)',
    display: 'flex',
    flexDirection: orientation === 'vertical' ? 'row' : 'column',
  }

  return (
    <TabsContext.Provider value={ctx}>
      <div className={className} style={rootStyles} role="tablist-container">
        {children}
      </div>
    </TabsContext.Provider>
  )
}

// ── TabList ──

export function TabList({ children, className }: TabListProps) {
  const { orientation } = useTabsContext()

  const listStyles: React.CSSProperties = {
    display: 'flex',
    flexDirection: orientation === 'vertical' ? 'column' : 'row',
    gap: 0,
    borderBottom: orientation === 'horizontal' ? '1px solid var(--color-border-default)' : 'none',
    borderRight: orientation === 'vertical' ? '1px solid var(--color-border-default)' : 'none',
    background: 'var(--color-bg-surface)',
  }

  return (
    <div
      className={className}
      style={listStyles}
      role="tablist"
      aria-orientation={orientation}
    >
      {children}
    </div>
  )
}

// ── Tab ──

export function Tab({ value, children, disabled = false, className }: TabProps) {
  const { activeTab, setActiveTab, size, orientation } = useTabsContext()
  const isActive = activeTab === value
  const s = tabSizeStyles[size]

  const tabStyles: React.CSSProperties = {
    fontFamily: 'var(--font-sans)',
    fontSize: s.fontSize,
    fontWeight: isActive ? 'var(--font-semibold)' : 'var(--font-medium)',
    lineHeight: 'var(--leading-tight)',
    color: isActive ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
    background: 'transparent',
    border: 'none',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.4 : 1,
    padding: `${s.paddingY} ${s.paddingX}`,
    position: 'relative',
    whiteSpace: 'nowrap',
    transition: 'var(--transition-fast)',
    display: 'flex',
    alignItems: 'center',
    // Active indicator — bottom bar for horizontal, right bar for vertical
    ...(orientation === 'horizontal'
      ? { borderBottom: isActive ? '2px solid var(--color-accent-blue)' : '2px solid transparent' }
      : { borderRight: isActive ? '2px solid var(--color-accent-blue)' : '2px solid transparent' }),
  }

  return (
    <button
      className={className}
      style={tabStyles}
      role="tab"
      aria-selected={isActive}
      aria-disabled={disabled}
      tabIndex={isActive ? 0 : -1}
      disabled={disabled}
      onClick={() => {
        if (!disabled) setActiveTab(value)
      }}
      onMouseEnter={(e) => {
        if (!disabled && !isActive) {
          e.currentTarget.style.color = 'var(--color-text-primary)'
          e.currentTarget.style.background = 'var(--color-bg-overlay)'
        }
      }}
      onMouseLeave={(e) => {
        if (!disabled && !isActive) {
          e.currentTarget.style.color = 'var(--color-text-secondary)'
          e.currentTarget.style.background = 'transparent'
        }
      }}
      onFocus={(e) => {
        if (!disabled && !isActive) {
          e.currentTarget.style.color = 'var(--color-text-primary)'
        }
      }}
      onBlur={(e) => {
        if (!disabled && !isActive) {
          e.currentTarget.style.color = 'var(--color-text-secondary)'
        }
      }}
    >
      {children}
    </button>
  )
}

// ── TabPanel ──

export function TabPanel({ value, children, className }: TabPanelProps) {
  const { activeTab, orientation } = useTabsContext()

  if (activeTab !== value) return null

  const panelStyles: React.CSSProperties = {
    fontFamily: 'var(--font-sans)',
    fontSize: 'var(--text-base)',
    lineHeight: 'var(--leading-normal)',
    color: 'var(--color-text-primary)',
    background: 'var(--color-bg-surface)',
    padding: 'var(--space-4)',
    borderRadius: 'var(--radius-md)',
    ...(orientation === 'horizontal'
      ? { borderTop: 'none' }
      : { borderLeft: 'none', marginLeft: 'var(--space-4)' }),
  }

  return (
    <div
      className={className}
      style={panelStyles}
      role="tabpanel"
      tabIndex={0}
    >
      {children}
    </div>
  )
}

export type { TabsContextValue }
