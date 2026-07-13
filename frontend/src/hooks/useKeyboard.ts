import { useEffect, useCallback } from 'react'

interface UseKeyboardOptions {
  onEscape?: () => void
  onArrowUp?: () => void
  onArrowDown?: () => void
  onEnter?: () => void
  onSlash?: () => void
  enabled?: boolean
}

export function useKeyboard({
  onEscape,
  onArrowUp,
  onArrowDown,
  onEnter,
  onSlash,
  enabled = true,
}: UseKeyboardOptions) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!enabled) return

      // Don't handle keyboard shortcuts when typing in input fields
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement
      ) {
        return
      }

      switch (e.key) {
        case 'Escape':
          onEscape?.()
          break
        case 'ArrowUp':
          e.preventDefault()
          onArrowUp?.()
          break
        case 'ArrowDown':
          e.preventDefault()
          onArrowDown?.()
          break
        case 'Enter':
          onEnter?.()
          break
        case '/':
          e.preventDefault()
          onSlash?.()
          break
      }
    },
    [enabled, onEscape, onArrowUp, onArrowDown, onEnter, onSlash]
  )

  useEffect(() => {
    if (!enabled) return

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [enabled, handleKeyDown])
}
