import { useState } from 'react'

interface ToolCallBlockProps {
  name: string
  arguments: string
}

function formatArguments(args: string): string {
  try {
    const parsed = JSON.parse(args)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return args
  }
}

export default function ToolCallBlock({ name, arguments: args }: ToolCallBlockProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="rounded-md border border-[#3d444d] bg-[#0d1117] overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[#161b22] transition-colors cursor-pointer"
      >
        <span className="text-[#f0883e] text-xs">⚡</span>
        <span className="text-[#e1e4e8] text-sm font-mono">{name}</span>
        <span className="text-[#8b949e] text-xs ml-auto">
          {expanded ? '▾' : '▸'}
        </span>
      </button>
      {expanded && (
        <div className="px-3 pb-3 border-t border-[#21262d]">
          <pre className="text-[12px] text-[#c9d1d9] overflow-x-auto mt-2 whitespace-pre-wrap break-all">
            {formatArguments(args)}
          </pre>
        </div>
      )}
    </div>
  )
}
