import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import type { StructuredMessage, MessageMetadata } from '../api/types'
import ToolCallBlock from './ToolCallBlock'
import ReasoningBlock from './ReasoningBlock'

interface MessageDisplayProps {
  messages: StructuredMessage[]
  metadata: MessageMetadata | null
}

function MessageBubble({ message }: { message: StructuredMessage }) {
  const roleColors: Record<string, string> = {
    system: 'bg-[#1c1c2e] border-[#3b3b5c] text-[#a0a0c0]',
    user: 'bg-[#1a2332] border-[#2d4a6f] text-[#c8daf0]',
    assistant: 'bg-[#1a2e1a] border-[#2d6f2d] text-[#c8e8c8]',
    tool: 'bg-[#2e2a1a] border-[#6f5f2d] text-[#e8dcc8]',
  }
  const roleLabels: Record<string, string> = {
    system: 'system',
    user: 'user',
    assistant: 'assistant',
    tool: 'tool',
  }

  return (
    <div className={`rounded-lg border p-4 mb-3 ${roleColors[message.role] || roleColors.assistant}`}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs font-mono opacity-70 uppercase tracking-wider">
          {roleLabels[message.role] || message.role}
        </span>
      </div>

      {message.reasoning_content && (
        <ReasoningBlock content={message.reasoning_content} />
      )}

      {message.content && (
        <div className="prose prose-invert prose-sm max-w-none">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
          >
            {message.content}
          </ReactMarkdown>
        </div>
      )}

      {!message.content && !message.reasoning_content && (
        <div className="text-[#8b949e] italic text-sm">(empty)</div>
      )}

      {message.tool_calls && message.tool_calls.length > 0 && (
        <div className="mt-3 space-y-2">
          {message.tool_calls.map((tc, i) => (
            <ToolCallBlock key={i} name={tc.name} arguments={tc.arguments} />
          ))}
        </div>
      )}
    </div>
  )
}

function MetadataBar({ metadata }: { metadata: MessageMetadata }) {
  if (!metadata) return null
  return (
    <div className="flex flex-wrap gap-2 mb-4 text-xs">
      {metadata.model && (
        <span className="px-2 py-1 rounded bg-[#30363d] text-[#58a6ff] font-mono">
          {metadata.model}
        </span>
      )}
      {metadata.finish_reason && (
        <span className="px-2 py-1 rounded bg-[#30363d] text-[#8b949e]">
          {metadata.finish_reason}
        </span>
      )}
      {metadata.usage && (
        <span className="px-2 py-1 rounded bg-[#30363d] text-[#8b949e]">
          {metadata.usage.input_tokens ?? '?'} in / {metadata.usage.output_tokens ?? '?'} out
        </span>
      )}
    </div>
  )
}

export default function MessageDisplay({ messages, metadata }: MessageDisplayProps) {
  if (!messages || messages.length === 0) {
    return (
      <div className="text-[#8b949e] italic text-sm py-4">
        No parsed messages available for this request.
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {metadata && <MetadataBar metadata={metadata} />}
      {messages.map((msg, i) => (
        <MessageBubble key={i} message={msg} />
      ))}
    </div>
  )
}
