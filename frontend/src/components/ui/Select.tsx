import { type SelectHTMLAttributes, type ReactNode, useRef } from 'react'

// ── Types ──

type SelectSize = 'sm' | 'md' | 'lg'

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  children: ReactNode
  size?: SelectSize
  placeholder?: string
  /** When true, shows a "none selected" state using the placeholder text */
  hasValue?: boolean
}

// ── Size tokens ──

const sizeStyles: Record<SelectSize, React.CSSProperties> = {
  sm: {
    padding: '4px 28px 4px 8px',
    fontSize: 'var(--text-sm)',
    lineHeight: 'var(--leading-tight)',
    borderRadius: 'var(--radius-sm)',
  },
  md: {
    padding: '6px 32px 6px 10px',
    fontSize: 'var(--text-base)',
    lineHeight: 'var(--leading-normal)',
    borderRadius: 'var(--radius-md)',
  },
  lg: {
    padding: '8px 36px 8px 12px',
    fontSize: 'var(--text-lg)',
    lineHeight: 'var(--leading-normal)',
    borderRadius: 'var(--radius-lg)',
  },
}

// ── Component ──

export default function Select({
  children,
  size = 'md',
  placeholder,
  hasValue = true,
  disabled = false,
  className = '',
  style,
  ...rest
}: SelectProps) {
  const ref = useRef<HTMLSelectElement>(null)

  const combinedStyle: React.CSSProperties = {
    fontFamily: 'var(--font-sans)',
    fontWeight: 'var(--font-normal)',
    color: hasValue ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
    background: 'var(--color-bg-overlay)',
    border: '1px solid var(--color-border-default)',
    outline: 'none',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
    appearance: 'none',
    WebkitAppearance: 'none',
    MozAppearance: 'none',
    backgroundImage:
      'url("data:image/svg+xml,%3Csvg width=\'10\' height=\'6\' viewBox=\'0 0 10 6\' fill=\'none\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cpath d=\'M1 1l4 4 4-4\' stroke=\'%238b949e\' stroke-width=\'1.5\' stroke-linecap=\'round\' stroke-linejoin=\'round\'/%3E%3C/svg%3E")',
    backgroundRepeat: 'no-repeat',
    backgroundPosition: `right ${size === 'sm' ? '8px' : size === 'md' ? '10px' : '12px'} center`,
    transition: 'var(--transition-fast)',
    ...sizeStyles[size],
    ...(style || {}),
  }

  return (
    <div
      className={`ui-select-wrapper ${className}`}
      style={{ position: 'relative', display: 'inline-flex' }}
    >
      <select
        ref={ref}
        disabled={disabled}
        style={combinedStyle}
        className="ui-select"
        {...rest}
      >
        {placeholder && (
          <option value="" disabled hidden>
            {placeholder}
          </option>
        )}
        {children}
      </select>
    </div>
  )
}

// ── Compound sub-components ──

interface SelectGroupProps {
  label?: string
  children: ReactNode
  className?: string
}

const groupLabelStyles: React.CSSProperties = {
  display: 'block',
  fontSize: 'var(--text-xs)',
  fontWeight: 'var(--font-medium)',
  color: 'var(--color-text-secondary)',
  marginBottom: 'var(--space-1)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
}

export function SelectGroup({ label, children, className = '' }: SelectGroupProps) {
  return (
    <div className={`ui-select-group ${className}`}>
      {label && <span style={groupLabelStyles}>{label}</span>}
      {children}
    </div>
  )
}

interface SelectOptionProps {
  value: string
  children: ReactNode
  disabled?: boolean
}

export function SelectOption({ value, children, disabled = false }: SelectOptionProps) {
  return (
    <option value={value} disabled={disabled}>
      {children}
    </option>
  )
}

// ── Type exports ──

export type { SelectProps, SelectSize }
