interface HeaderProps {
  requestCount: number | null
  loading: boolean
}

export default function Header({ requestCount, loading }: HeaderProps) {
  const statusText = loading
    ? 'Loading...'
    : requestCount !== null
      ? `${requestCount.toLocaleString()} requests`
      : 'No data'

  return (
    <header className="bg-[#161b22] border-b border-[#30363d] px-6 py-4 flex justify-between items-center">
      <h1 className="text-lg font-semibold">otel-agent Dashboard</h1>
      <span className="text-sm text-[#8b949e]">{statusText}</span>
    </header>
  )
}
