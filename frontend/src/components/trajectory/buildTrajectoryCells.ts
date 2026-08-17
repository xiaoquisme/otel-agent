import type { StructuredMessage } from '../../api/types'

export type TrajectoryKind = 'SYSTEM' | 'USER' | 'ASSISTANT' | 'TOOL' | 'REASONING'

export interface TrajectoryCell {
  id: string
  index: number
  kind: TrajectoryKind
  preview: string
  message: StructuredMessage
  toolCall?: { id?: string; name: string; arguments: string }
}

function oneLine(text: string, max = 160): string {
  const collapsed = text.replace(/\s+/g, ' ').trim()
  if (collapsed.length <= max) return collapsed
  return `${collapsed.slice(0, max - 1)}…`
}

function kindForRole(role: string): TrajectoryKind {
  if (role === 'system') return 'SYSTEM'
  if (role === 'user') return 'USER'
  if (role === 'tool') return 'TOOL'
  return 'ASSISTANT'
}

export function buildTrajectoryCells(messages: StructuredMessage[]): TrajectoryCell[] {
  const cells: TrajectoryCell[] = []
  let index = 1

  for (let i = 0; i < messages.length; i++) {
    const message = messages[i]
    const before = cells.length
    if (message.reasoning_content) {
      cells.push({
        id: `${i}-reasoning`,
        index: index++,
        kind: 'REASONING',
        preview: oneLine(message.reasoning_content),
        message,
      })
    }

    if (message.content) {
      cells.push({
        id: `${i}-${message.role}`,
        index: index++,
        kind: kindForRole(message.role),
        preview: oneLine(message.content),
        message,
      })
    }

    if (message.tool_calls) {
      for (let t = 0; t < message.tool_calls.length; t++) {
        const toolCall = message.tool_calls[t]
        cells.push({
          id: `${i}-tool-${toolCall.id ?? t}`,
          index: index++,
          kind: 'TOOL',
          preview: oneLine(`${toolCall.name} ${toolCall.arguments}`),
          message,
          toolCall,
        })
      }
    }

    if (cells.length === before) {
      cells.push({
        id: `${i}-${message.role}`,
        index: index++,
        kind: kindForRole(message.role),
        preview: '',
        message,
      })
    }
  }

  return cells
}
