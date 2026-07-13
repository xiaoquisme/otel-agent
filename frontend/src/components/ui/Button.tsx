import { type ButtonHTMLAttributes, type ReactNode } from 'react'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
type ButtonSize = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  children: ReactNode
}

const variantStyles: Record<ButtonVariant, Record<string, string>> = {
  primary: {
    background: 'var(--color-accent-blue)',
    color: 'var(--color-text-inverse)',
    border: '1px solid var(--color-accent-blue)',
  },
  secondary: {
    background: 'var(--color-bg-overlay)',
    color: 'var(--color-text-primary)',
    border: '1px solid var(--color-border-default)',
  },
  ghost: {
    background: 'transparent',
    color: 'var(--color-text-primary)',
    border: '1px solid transparent',
  },
  danger: {
    background: 'var(--color-accent-red)',
    color: '#fff',
    border: '1px solid var(--color-accent-red)',
  },
}

const variantHoverStyles: Record<ButtonVariant, string> = {
  primary: 'var(--color-accent-blue-muted)',
  secondary: 'var(--color-bg-muted)',
  ghost: 'var(--color-bg-muted)',
  danger: 'var(--color-accent-red-muted)',
}

const sizeStyles: Record<ButtonSize, Record<string, string>> = {
  sm: {
    padding: '4px 10px',
    fontSize: 'var(--text-sm)',
    lineHeight: 'var(--leading-tight)',
    borderRadius: 'var(--radius-sm)',
  },
  md: {
    padding: '8px 16px',
    fontSize: 'var(--text-base)',
    lineHeight: 'var(--leading-normal)',
    borderRadius: 'var(--radius-md)',
  },
  lg: {
    padding: '12px 24px',
    fontSize: 'var(--text-lg)',
    lineHeight: 'var(--leading-normal)',
    borderRadius: 'var(--radius-lg)',
  },
}

function Spinner({ size }: { size: ButtonSize }) {
  const spinnerSize = size === 'sm' ? 12 : size === 'md' ? 16 : 20
  return (
    <svg
      className="btn-spinner"
      width={spinnerSize}
      height={spinnerSize}
      viewBox="0 0 24 24"
      fill="none"
      style={{ animation: 'spin 0.6s linear infinite', marginRight: '6px' }}
    >
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeOpacity="0.3"
        strokeWidth="3"
      />
      <path
        d="M12 2a10 10 0 0 1 10 10"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  )
}

export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  children,
  style,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading

  const combinedStyle: React.CSSProperties = {
    fontFamily: 'var(--font-sans)',
    fontWeight: 'var(--font-medium)',
    cursor: isDisabled ? 'not-allowed' : 'pointer',
    opacity: isDisabled ? 0.5 : 1,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '4px',
    whiteSpace: 'nowrap',
    transition: 'var(--transition-fast)',
    ...variantStyles[variant],
    ...sizeStyles[size],
    ...(style || {}),
  }

  return (
    <button
      className="ui-button"
      disabled={isDisabled}
      style={combinedStyle}
      onMouseEnter={(e) => {
        if (!isDisabled) {
          e.currentTarget.style.background = variantHoverStyles[variant]
        }
      }}
      onMouseLeave={(e) => {
        if (!isDisabled) {
          e.currentTarget.style.background = variantStyles[variant].background
        }
      }}
      {...rest}
    >
      {loading && <Spinner size={size} />}
      {children}
    </button>
  )
}

export type { ButtonProps, ButtonVariant, ButtonSize }
