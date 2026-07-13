import React, { useCallback, useEffect, useRef, useState } from 'react'

// ── Types ──

export interface SearchInputProps {
  /** Current controlled value */
  value?: string
  /** Default uncontrolled value */
  defaultValue?: string
  /** Callback fired after the debounce delay (ms) */
  onChange: (value: string) => void
  /** Debounce delay in ms (default 300) */
  debounceMs?: number
  /** Placeholder text */
  placeholder?: string
  /** Whether the input is disabled */
  disabled?: boolean
  /** Additional class names for the outer wrapper */
  className?: string
  /** Accessible label for the input */
  'aria-label'?: string
}

// ── Hooks ──

function useDebouncedCallback(
  callback: (value: string) => void,
  delay: number,
): (value: string) => void {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const callbackRef = useRef(callback)
  callbackRef.current = callback

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current)
    }
  }, [])

  return useCallback(
    (value: string) => {
      if (timerRef.current !== null) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => callbackRef.current(value), delay)
    },
    [delay],
  )
}

// ── SVG Icons (inline, no external deps) ──

function SearchIcon({ style }: { style: React.CSSProperties }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={style}
      aria-hidden="true"
    >
      <path
        d="M7.333 12.667A5.333 5.333 0 1 0 7.333 2a5.333 5.333 0 0 0 0 10.667ZM14 14l-2.9-2.9"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function ClearIcon({ style }: { style: React.CSSProperties }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={style}
      aria-hidden="true"
    >
      <path
        d="M10.5 3.5L3.5 10.5M3.5 3.5l7 7"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

// ── Styles using CSS custom properties ──

const wrapperBase: React.CSSProperties = {
  position: 'relative',
  display: 'inline-flex',
  alignItems: 'center',
  width: '100%',
  fontFamily: 'var(--font-sans)',
}

const inputBase: React.CSSProperties = {
  width: '100%',
  height: '36px',
  padding: '0 var(--space-9) 0 var(--space-8)',
  margin: 0,
  background: 'var(--color-bg-surface)',
  border: '1px solid var(--color-border-default)',
  borderRadius: 'var(--radius-md)',
  color: 'var(--color-text-primary)',
  fontFamily: 'var(--font-sans)',
  fontSize: 'var(--text-sm)',
  lineHeight: 'var(--leading-normal)',
  outline: 'none',
  transition: 'border-color var(--transition-fast), box-shadow var(--transition-fast)',
}

const inputFocus: React.CSSProperties = {
  borderColor: 'var(--color-accent-blue)',
  boxShadow: '0 0 0 2px var(--color-accent-blue-muted)',
}

const inputDisabled: React.CSSProperties = {
  opacity: 0.5,
  cursor: 'not-allowed',
}

const iconLeftStyle: React.CSSProperties = {
  position: 'absolute',
  left: 'var(--space-3)',
  top: '50%',
  transform: 'translateY(-50%)',
  color: 'var(--color-text-muted)',
  pointerEvents: 'none',
  display: 'flex',
  alignItems: 'center',
}

const clearButtonBase: React.CSSProperties = {
  position: 'absolute',
  right: 'var(--space-2)',
  top: '50%',
  transform: 'translateY(-50%)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '24px',
  height: '24px',
  padding: 0,
  margin: 0,
  background: 'transparent',
  border: 'none',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--color-text-muted)',
  cursor: 'pointer',
  transition: 'color var(--transition-fast), background var(--transition-fast)',
  flexShrink: 0,
}

const clearButtonHover: React.CSSProperties = {
  color: 'var(--color-text-primary)',
  background: 'var(--color-bg-muted)',
}

// ── Component ──

export function SearchInput({
  value: controlledValue,
  defaultValue = '',
  onChange,
  debounceMs = 300,
  placeholder = 'Search…',
  disabled = false,
  className,
  'aria-label': ariaLabel = 'Search',
}: SearchInputProps) {
  const isControlled = controlledValue !== undefined
  const [internalValue, setInternalValue] = useState(defaultValue)
  const [isFocused, setIsFocused] = useState(false)
  const [clearHovered, setClearHovered] = useState(false)

  const displayValue = isControlled ? controlledValue : internalValue

  const debouncedOnChange = useDebouncedCallback(onChange, debounceMs)

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const newValue = e.target.value
      if (!isControlled) {
        setInternalValue(newValue)
      }
      debouncedOnChange(newValue)
    },
    [isControlled, debouncedOnChange],
  )

  const handleClear = useCallback(() => {
    if (!isControlled) {
      setInternalValue('')
    }
    onChange('')
  }, [isControlled, onChange])

  // Sync controlled value changes
  useEffect(() => {
    if (isControlled) {
      setInternalValue(controlledValue)
    }
  }, [isControlled, controlledValue])

  const wrapperStyle: React.CSSProperties = {
    ...wrapperBase,
  }

  const inputStyle: React.CSSProperties = {
    ...inputBase,
    ...(isFocused && !disabled ? inputFocus : {}),
    ...(disabled ? inputDisabled : {}),
  }

  const clearBtnStyle: React.CSSProperties = {
    ...clearButtonBase,
    ...(clearHovered && !disabled ? clearButtonHover : {}),
    ...(disabled ? { pointerEvents: 'none' as const, opacity: 0.5 } : {}),
  }

  return (
    <div className={className} style={wrapperStyle}>
      {/* Scoped placeholder styles */}
      <style>{`
        .otel-search-input::placeholder { color: var(--color-text-muted); }
      `}</style>

      <span style={iconLeftStyle}>
        <SearchIcon style={{}} />
      </span>

      <input
        type="text"
        className="otel-search-input"
        style={inputStyle}
        value={displayValue}
        onChange={handleChange}
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
        placeholder={placeholder}
        disabled={disabled}
        aria-label={ariaLabel}
        autoComplete="off"
        spellCheck={false}
      />

      {displayValue && !disabled && (
        <button
          type="button"
          style={clearBtnStyle}
          onClick={handleClear}
          onMouseEnter={() => setClearHovered(true)}
          onMouseLeave={() => setClearHovered(false)}
          aria-label="Clear search"
        >
          <ClearIcon style={{}} />
        </button>
      )}
    </div>
  )
}

export default SearchInput
