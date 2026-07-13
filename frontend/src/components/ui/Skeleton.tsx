import { type HTMLAttributes } from 'react'

interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  width?: string | number
  height?: string | number
  rounded?: boolean
}

export default function Skeleton({
  width,
  height = '1em',
  rounded = false,
  className = '',
  ...props
}: SkeletonProps) {
  return (
    <div
      className={`animate-pulse ${rounded ? 'rounded-full' : 'rounded'} ${className}`}
      style={{
        width,
        height,
        backgroundColor: 'var(--color-bg-overlay)',
        ...props.style,
      }}
      {...props}
    />
  )
}

export function SkeletonText({ lines = 3, className = '' }: { lines?: number; className?: string }) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          height="14px"
          width={i === lines - 1 ? '60%' : '100%'}
        />
      ))}
    </div>
  )
}

export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div
      className={`p-4 rounded-lg ${className}`}
      style={{ backgroundColor: 'var(--color-bg-surface)', border: '1px solid var(--color-border-default)' }}
    >
      <SkeletonText lines={2} />
    </div>
  )
}
