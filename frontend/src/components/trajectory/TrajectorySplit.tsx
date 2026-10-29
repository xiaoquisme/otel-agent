import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from 'react'
import {
  clampDetailsWidth,
  MIN_DETAILS_PX,
  MIN_LEDGER_PX,
  readStoredDetailsWidth,
  writeStoredDetailsWidth,
} from './detailsWidth'

interface TrajectorySplitProps {
  ledger: ReactNode
  details: ReactNode
}

export default function TrajectorySplit({ ledger, details }: TrajectorySplitProps) {
  const splitRef = useRef<HTMLDivElement>(null)
  const preferredRef = useRef<number | null>(null)
  const draggingRef = useRef(false)
  const grabOffsetRef = useRef(0)
  const [preferred, setPreferred] = useState<number | null>(() => readStoredDetailsWidth())
  const [dragging, setDragging] = useState(false)
  const [container, setContainer] = useState(0)
  const [fallbackWidth, setFallbackWidth] = useState(MIN_DETAILS_PX)

  preferredRef.current = preferred

  const applied =
    preferred == null || container <= 0 ? null : clampDetailsWidth(preferred, container)

  useLayoutEffect(() => {
    const el = splitRef.current
    if (!el) return
    const update = () => setContainer(el.clientWidth)
    update()
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  useLayoutEffect(() => {
    if (applied != null) return
    const aside = splitRef.current?.querySelector('.dsh-details')
    if (!(aside instanceof HTMLElement)) return
    const width = Math.round(aside.getBoundingClientRect().width)
    if (width > 0) setFallbackWidth(width)
  }, [applied, container])

  useEffect(() => {
    if (!dragging) return
    const { style } = document.body
    const previousCursor = style.cursor
    const previousUserSelect = style.userSelect
    style.cursor = 'col-resize'
    style.userSelect = 'none'
    return () => {
      style.cursor = previousCursor
      style.userSelect = previousUserSelect
    }
  }, [dragging])

  const commit = (next: number | null, persist: boolean) => {
    preferredRef.current = next
    setPreferred(next)
    if (persist) writeStoredDetailsWidth(next)
  }

  const measureDetails = () => {
    const aside = splitRef.current?.querySelector('.dsh-details')
    if (!(aside instanceof HTMLElement)) return applied ?? fallbackWidth
    const width = Math.round(aside.getBoundingClientRect().width)
    return width > 0 ? width : (applied ?? fallbackWidth)
  }

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || !splitRef.current) return
    event.preventDefault()
    const rect = splitRef.current.getBoundingClientRect()
    const current = measureDetails()
    grabOffsetRef.current = rect.right - event.clientX - current
    draggingRef.current = true
    setDragging(true)
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current || !splitRef.current) return
    const rect = splitRef.current.getBoundingClientRect()
    const requested = rect.right - event.clientX - grabOffsetRef.current
    commit(clampDetailsWidth(requested, rect.width), false)
  }

  const finishDrag = () => {
    if (!draggingRef.current) return
    draggingRef.current = false
    setDragging(false)
    writeStoredDetailsWidth(preferredRef.current)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const rect = splitRef.current?.getBoundingClientRect()
    const width = rect?.width ?? container
    const current = measureDetails()
    const step = event.shiftKey ? 80 : 24
    let next: number | null = null
    if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = current + step
    else if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = current - step
    else if (event.key === 'Home') next = MIN_DETAILS_PX
    else if (event.key === 'End') next = width > 0 ? width - MIN_LEDGER_PX : current
    else return
    event.preventDefault()
    event.stopPropagation()
    commit(clampDetailsWidth(next, width), true)
  }

  const max = container > 0 ? Math.max(0, Math.round(container - MIN_LEDGER_PX)) : Math.max(MIN_DETAILS_PX, fallbackWidth)
  const min = container > 0 ? Math.min(MIN_DETAILS_PX, max) : MIN_DETAILS_PX
  const valueNow = Math.round(applied ?? fallbackWidth)
  const style: CSSProperties | undefined =
    applied == null
      ? undefined
      : ({ '--dsh-details-width': `${applied}px` } as CSSProperties)

  return (
    <div
      ref={splitRef}
      className="dsh-split"
      data-dragging={dragging ? 'true' : undefined}
      style={style}
    >
      {ledger}
      <div
        className="dsh-split-handle"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize event details"
        aria-controls="dsh-event-details"
        aria-valuemin={min}
        aria-valuemax={Math.max(min, max)}
        aria-valuenow={Math.min(Math.max(valueNow, min), Math.max(min, max))}
        title="Drag to resize the detail panel. Double-click to reset."
        tabIndex={0}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={finishDrag}
        onPointerCancel={finishDrag}
        onLostPointerCapture={finishDrag}
        onDoubleClick={() => commit(null, true)}
        onKeyDown={onKeyDown}
      />
      {details}
    </div>
  )
}
