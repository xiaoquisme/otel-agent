/** Matches ``otel_agent.sessions.INFERRED_SESSION_PREFIX``. */
export const INFERRED_SESSION_PREFIX = 'inferred-'

export function isInferredSession(sessionId: string | null | undefined): boolean {
  return typeof sessionId === 'string' && sessionId.startsWith(INFERRED_SESSION_PREFIX)
}

/** Route for the session trajectory. The id is one path segment, even with slashes. */
export function sessionPath(sessionId: string): string {
  return `/sessions/${encodeURIComponent(sessionId)}`
}
