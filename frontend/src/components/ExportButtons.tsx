import { exportData } from '../api/client'
import type { RequestListParams } from '../api/types'

interface ExportButtonsProps {
  currentParams: RequestListParams
}

export default function ExportButtons({ currentParams }: ExportButtonsProps) {
  return (
    <>
      <button
        className="bg-[#21262d] border border-[#30363d] text-white px-4 py-2 rounded-md text-sm cursor-pointer hover:bg-[#30363d]"
        onClick={() => exportData('csv', currentParams)}
      >
        Export CSV
      </button>
      <button
        className="bg-[#21262d] border border-[#30363d] text-white px-4 py-2 rounded-md text-sm cursor-pointer hover:bg-[#30363d]"
        onClick={() => exportData('json', currentParams)}
      >
        Export JSON
      </button>
    </>
  )
}
