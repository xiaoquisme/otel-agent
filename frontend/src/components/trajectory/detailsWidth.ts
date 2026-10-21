/** Right inspector stays wide enough to read the tab strip. */
export const MIN_DETAILS_PX = 320

/** Ledger keeps index, kind tag, and a sliver of preview. */
export const MIN_LEDGER_PX = 280

export const DETAILS_WIDTH_STORAGE_KEY = 'otel-agent.dsh-details-width'

/**
 * Clamp the event-details pane so neither side of the horizontal split collapses.
 * A zero container means layout has not been measured yet; keep the requested
 * width (or the details minimum) until the split element has a size.
 */
export function clampDetailsWidth(requested: number, containerWidth: number): number {
  const safe = Number.isFinite(requested) ? requested : MIN_DETAILS_PX
  if (!Number.isFinite(containerWidth) || containerWidth <= 0) {
    return Math.max(MIN_DETAILS_PX, Math.round(safe))
  }
  const max = Math.max(0, containerWidth - MIN_LEDGER_PX)
  const min = Math.min(MIN_DETAILS_PX, max)
  return Math.round(Math.min(Math.max(safe, min), max))
}

export function readStoredDetailsWidth(): number | null {
  try {
    const raw = localStorage.getItem(DETAILS_WIDTH_STORAGE_KEY)
    if (raw == null || raw.trim() === '') return null
    const value = Number(raw)
    if (!Number.isFinite(value) || value <= 0) return null
    return value
  } catch {
    return null
  }
}

export function writeStoredDetailsWidth(width: number | null): void {
  try {
    if (width == null) localStorage.removeItem(DETAILS_WIDTH_STORAGE_KEY)
    else localStorage.setItem(DETAILS_WIDTH_STORAGE_KEY, String(Math.round(width)))
  } catch {
    /* Private mode or blocked storage: in-session resize still works. */
  }
}
