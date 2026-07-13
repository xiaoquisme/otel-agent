import { useState } from 'react'

interface ReasoningBlockProps {
  content: string
}

export default function ReasoningBlock({ content }: ReasoningBlockProps) {
  const [expanded, setExpanded] = useState(false)

  if (!content) return null

  return (
    <div className="rounded-md border border-[#2d333b] bg-[#0d1117] mb-3 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[#161b22] transition-colors cursor-pointer"
      >
        <span className="text-[#a371f7] text-xs">💭</span>
        <span className="text-[#a371f7] text-sm">Reasoning</span>
        <span className="text-[#8b949e] text-xs ml-auto">
          {expanded ? '▾' : '▸'}
        </span>
      </button>
      {expanded && (
        <div className="px-3 pb-3 border-t border-[#21262d]">
          <div className="text-[13px] text-[#8b949e] mt-2 whitespace-pre-wrap leading-relaxed">
            {content}
          </div>
        </div>
      )}
    </div>
  )
}
