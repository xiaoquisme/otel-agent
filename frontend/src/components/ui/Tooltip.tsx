import React, { useState, useRef, useCallback } from 'react'

// ── Types ──

type TooltipPlacement = 'top' | 'bottom' | 'left' | 'right'

interface TooltipProps {
  /** The element that triggers the tooltip */
  children: React.ReactElement
  /** Tooltip content — string or ReactNode */
  content: React.ReactNode
  /** Placement relative to the trigger */
  placement?: TooltipPlacement
  /** Delay in ms before showing the tooltip */
  delayMs?: number
  /** Additional class name for the tooltip wrapper */
  className?: string
  /** Disabled — never show the tooltip */
  disabled?: boolean
}

// ── Token-derived inline styles ──

const tooltipBaseStyle: React.CSSProperties = {
  position: 'absolute',
  zIndex: 'var(--z-toast)' as unknown as number,
  padding: 'var(--space-1) var(--space-2)',
  borderRadius: 'var(--radius-md)',
  background: 'var(--color-bg-overlay)',
  border: '1px solid var(--color-border-emphasis)',
  boxShadow: 'var(--shadow-md)',
  color: 'var(--color-text-primary)',
  fontFamily: 'var(--font-sans)',
  fontSize: 'var(--text-xs)',
  fontWeight: 'var(--font-normal)',
  lineHeight: 'var(--leading-normal)',
  whiteSpace: 'nowrap',
  pointerEvents: 'none',
  opacity: 0,
  transition: 'opacity var(--transition-fast)',
}

const visibleStyle: React.CSSProperties = {
  opacity: 1,
}

// ── Placement offsets (distance from the trigger element's edge) ──

const OFFSET = 8

function placementStyles(placement: TooltipPlacement): React.CSSProperties {
  switch (placement) {
    case 'top':
      return {
        bottom: '100%',
        left: '50%',
        transform: `translateX(-50%) translateY(-${OFFSET}px)`,
      }
    case 'bottom':
      return {
        top: '100%',
        left: '50%',
        transform: `translateX(-50%) translateY(${OFFSET}px)`,
      }
    case 'left':
      return {
        right: '100%',
        top: '50%',
        transform: `translateY(-50%) translateX(-${OFFSET}px)`,
      }
    case 'right':
      return {
        left: '100%',
        top: '50%',
        transform: `translateY(-50%) translateX(${OFFSET}px)`,
      }
  }
}

// ── Component ──

export type { TooltipProps }

export default function Tooltip({
  children,
  content,
  placement = 'top',
  delayMs = 300,
  className = '',
  disabled = false,
}: TooltipProps) {
  const [visible, setVisible] = useState(false)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const show = useCallback(() => {
    if (disabled) return
    timeoutRef.current = setTimeout(() => setVisible(true), delayMs)
  }, [disabled, delayMs])

  const hide = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
    setVisible(false)
  }, [])

  const wrapperStyle: React.CSSProperties = {
    position: 'relative',
    display: 'inline-flex',
  }

  const tooltipStyle: React.CSSProperties = {
    ...tooltipBaseStyle,
    ...placementStyles(placement),
    ...(visible ? visibleStyle : {}),
  }

  if (!content || disabled) {
    return children
  }

  return (
    <span
      className={className}
      style={wrapperStyle}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {children}
      <span role="tooltip" style={tooltipStyle} aria-hidden={!visible}>
        {content}
      </span>
    </span>
  )
}
