import type { HTMLAttributes, ReactNode } from 'react'

export type BadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'info' | 'purple'
export type BadgeSize = 'sm' | 'md'

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  children: ReactNode
  variant?: BadgeVariant
  size?: BadgeSize
}

const variantStyles: Record<BadgeVariant, { bg: string; text: string; border: string }> = {
  default: {
    bg: 'var(--color-bg-muted)',
    text: 'var(--color-text-secondary)',
    border: 'var(--color-border-default)',
  },
  success: {
    bg: 'var(--color-accent-green-muted)',
    text: 'var(--color-accent-green)',
    border: 'var(--color-accent-green)',
  },
  warning: {
    bg: 'var(--color-accent-yellow-muted)',
    text: 'var(--color-accent-yellow)',
    border: 'var(--color-accent-yellow)',
  },
  error: {
    bg: 'var(--color-accent-red-muted)',
    text: 'var(--color-accent-red)',
    border: 'var(--color-accent-red)',
  },
  info: {
    bg: 'var(--color-accent-blue-muted)',
    text: 'var(--color-accent-blue)',
    border: 'var(--color-accent-blue)',
  },
  purple: {
    bg: 'var(--color-accent-purple-muted)',
    text: 'var(--color-accent-purple)',
    border: 'var(--color-accent-purple)',
  },
}

const sizeStyles: Record<BadgeSize, { fontSize: string; paddingX: string; paddingY: string; lineHeight: string }> = {
  sm: {
    fontSize: 'var(--text-xs)',
    paddingX: 'var(--space-1)',
    paddingY: '2px',
    lineHeight: '1.4',
  },
  md: {
    fontSize: 'var(--text-sm)',
    paddingX: 'var(--space-2)',
    paddingY: 'var(--space-0.5, 2px)',
    lineHeight: 'var(--leading-tight)',
  },
}

export default function Badge({
  children,
  variant = 'default',
  size = 'md',
  style,
  className = '',
  ...rest
}: BadgeProps) {
  const v = variantStyles[variant]
  const s = sizeStyles[size]

  return (
    <span
      className={`inline-flex items-center font-medium whitespace-nowrap ${className}`}
      style={{
        backgroundColor: v.bg,
        color: v.text,
        border: `1px solid ${v.border}`,
        borderRadius: 'var(--radius-full)',
        fontSize: s.fontSize,
        paddingLeft: s.paddingX,
        paddingRight: s.paddingX,
        paddingTop: s.paddingY,
        paddingBottom: s.paddingY,
        lineHeight: s.lineHeight,
        fontFamily: 'var(--font-sans)',
        ...style,
      }}
      {...rest}
    >
      {children}
    </span>
  )
}
