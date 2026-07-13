import React from 'react'

// ── Types ──

type CardPadding = 'sm' | 'md' | 'lg'

interface CardProps {
  children: React.ReactNode
  padding?: CardPadding
  hoverable?: boolean
  clickable?: boolean
  className?: string
  style?: React.CSSProperties
  onClick?: () => void
}

// ── Padding map using tokens.css custom properties ──

const paddingMap: Record<CardPadding, string> = {
  sm: 'var(--space-3)',
  md: 'var(--space-4)',
  lg: 'var(--space-6)',
}

// ── Inline styles using CSS custom properties ──

const baseStyles: React.CSSProperties = {
  background: 'var(--color-bg-surface)',
  border: '1px solid var(--color-border-default)',
  borderRadius: 'var(--radius-lg)',
  boxShadow: 'var(--shadow-sm)',
  transition: 'var(--transition-base)',
  fontFamily: 'var(--font-sans)',
  fontSize: 'var(--text-base)',
  lineHeight: 'var(--leading-normal)',
}

const hoverStyles: React.CSSProperties = {
  boxShadow: 'var(--shadow-md)',
  borderColor: 'var(--color-border-emphasis)',
}

const clickableStyles: React.CSSProperties = {
  cursor: 'pointer',
  userSelect: 'none',
}

const activeStyles: React.CSSProperties = {
  transform: 'scale(0.995)',
  boxShadow: 'var(--shadow-sm)',
}

// ── Component ──

export function Card({
  children,
  padding = 'md',
  hoverable = false,
  clickable = false,
  className,
  style: externalStyle,
  onClick,
}: CardProps) {
  const [isHovered, setIsHovered] = React.useState(false)
  const [isActive, setIsActive] = React.useState(false)

  const style: React.CSSProperties = {
    ...baseStyles,
    padding: paddingMap[padding],
    ...(clickable && isHovered ? hoverStyles : {}),
    ...(hoverable && isHovered ? hoverStyles : {}),
    ...(clickable ? clickableStyles : {}),
    ...(isActive ? activeStyles : {}),
    ...externalStyle,
  }

  const handleMouseEnter = () => setIsHovered(true)
  const handleMouseLeave = () => {
    setIsHovered(false)
    setIsActive(false)
  }
  const handleMouseDown = () => setIsActive(true)
  const handleMouseUp = () => setIsActive(false)

  return (
    <div
      className={className}
      style={style}
      onClick={onClick}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onMouseDown={clickable ? handleMouseDown : undefined}
      onMouseUp={clickable ? handleMouseUp : undefined}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={
        clickable
          ? (e: React.KeyboardEvent) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onClick?.()
              }
            }
          : undefined
      }
    >
      {children}
    </div>
  )
}

// ── Compound sub-components ──

interface CardSectionProps {
  children: React.ReactNode
  className?: string
}

const sectionStyles: React.CSSProperties = {
  borderTop: '1px solid var(--color-border-muted)',
  margin: 'calc(-1 * var(--space-4)) 0 0',
  padding: 'var(--space-4)',
}

export function CardSection({ children, className }: CardSectionProps) {
  return (
    <div className={className} style={sectionStyles}>
      {children}
    </div>
  )
}

interface CardHeaderProps {
  children: React.ReactNode
  className?: string
}

const headerStyles: React.CSSProperties = {
  marginBottom: 'var(--space-3)',
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-2)',
}

export function CardHeader({ children, className }: CardHeaderProps) {
  return (
    <div className={className} style={headerStyles}>
      {children}
    </div>
  )
}

interface CardTitleProps {
  children: React.ReactNode
  className?: string
}

const titleStyles: React.CSSProperties = {
  fontSize: 'var(--text-lg)',
  fontWeight: 'var(--font-semibold)',
  color: 'var(--color-text-primary)',
  margin: 0,
  lineHeight: 'var(--leading-tight)',
}

export function CardTitle({ children, className }: CardTitleProps) {
  return (
    <h3 className={className} style={titleStyles}>
      {children}
    </h3>
  )
}

interface CardDescriptionProps {
  children: React.ReactNode
  className?: string
}

const descriptionStyles: React.CSSProperties = {
  fontSize: 'var(--text-sm)',
  color: 'var(--color-text-secondary)',
  margin: 0,
}

export function CardDescription({ children, className }: CardDescriptionProps) {
  return (
    <p className={className} style={descriptionStyles}>
      {children}
    </p>
  )
}
