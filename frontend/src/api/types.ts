export interface RequestItem {
  id: number
  timestamp: string
  method: string
  url: string
  upstream: string | null
  response_status: number
  latency_ms: number | null
  format: string | null
  model_name: string | null
}

export interface StructuredMessage {
  role: string
  content: string
  tool_calls?: { id?: string; name: string; arguments: string }[]
  reasoning_content?: string
}

export interface MessageMetadata {
  model: string | null
  finish_reason: string | null
  usage: { input_tokens: number | null; output_tokens: number | null; total_tokens: number | null } | null
  format: string | null
}

export interface RequestDetail extends RequestItem {
  request_body: string | null
  response_body: string | null
  request_headers: Record<string, string> | string | null
  response_headers: Record<string, string> | string | null
  messages: StructuredMessage[]
  metadata: MessageMetadata
}

export interface RequestsResponse {
  data: RequestItem[]
  total: number
  cursor: number
  next_cursor: number | null
  has_more: boolean
}

export interface ModelUsage {
  model_name: string | null
  total_tokens: number
  input_tokens: number
  output_tokens: number
  request_count: number
}

export interface UsageSummary {
  start: string
  end: string
  total_tokens: number
  input_tokens: number
  output_tokens: number
  models: ModelUsage[]
  eligible_request_count: number
  excluded_request_count: number
}

export interface RequestListParams {
  search?: string
  method?: string
  status?: number
  cursor?: number
  limit?: number
}

export interface ExportFormat {
  format: 'csv' | 'json'
}
