import type { SessionStep } from '../api/types'

/** Matches ``otel_agent.sessions.INFERRED_SESSION_PREFIX``. */
export const INFERRED_SESSION_PREFIX = 'inferred-'

export function isInferredSession(sessionId: string | null | undefined): boolean {
  return typeof sessionId === 'string' && sessionId.startsWith(INFERRED_SESSION_PREFIX)
}

/** Route for the session trajectory. The id is one path segment, even with slashes. */
export function sessionPath(sessionId: string): string {
  return `/sessions/${encodeURIComponent(sessionId)}`
}

export interface SessionTurnGroup {
  index: number
  label: string | null
  steps: { step: SessionStep; number: number }[]
}

/** Group an already chronological step list by the server's turn index. */
export function groupSessionTurns(steps: SessionStep[]): SessionTurnGroup[] {
  const turns: SessionTurnGroup[] = []
  steps.forEach((step, offset) => {
    const index = step.turn_index > 0 ? step.turn_index : offset + 1
    const current = turns[turns.length - 1]
    if (!current || current.index !== index) {
      turns.push({ index, label: step.turn_label ?? null, steps: [] })
    }
    const turn = turns[turns.length - 1]
    if (!turn.label && step.turn_label) turn.label = step.turn_label
    turn.steps.push({ step, number: offset + 1 })
  })
  return turns
}
