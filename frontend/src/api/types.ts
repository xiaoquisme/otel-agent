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
  /** Agent run this call belongs to. Null when the row has no session. */
  session_id?: string | null
  /** Optional turn label from X-Otel-Session-Step. Never invented. */
  session_step?: string | null
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
  cache_read_tokens?: number
  cache_creation_tokens?: number
  cacheable_input_tokens?: number
  cache_hit_rate?: number | null
}

export type UsageBucket = 'hour' | 'day' | 'week' | 'month'

export interface UsageSeriesPoint {
  bucket_start: string
  input_tokens: number
  output_tokens: number
  total_tokens: number
  request_count: number
}

export interface UsageSeries {
  start: string
  end: string
  bucket: UsageBucket
  timezone: string
  points: UsageSeriesPoint[]
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
  cache_read_tokens?: number
  cache_creation_tokens?: number
  cacheable_input_tokens?: number
  cache_hit_rate?: number | null
}

export interface SessionSummary {
  session_id: string
  request_count: number
  total_tokens: number
  input_tokens: number
  output_tokens: number
  token_request_count: number
  first_timestamp: string
  last_timestamp: string
  error_count: number
  total_latency_ms: number
  models: string[]
  upstreams: string[]
}

export interface SessionStep {
  id: number
  timestamp: string
  method: string
  url: string
  upstream: string | null
  response_status: number | null
  latency_ms: number | null
  model_name: string | null
  input_tokens: number | null
  output_tokens: number | null
  total_tokens: number | null
  cache_read_tokens: number | null
  cache_creation_tokens: number | null
  format: string | null
  session_step: string | null
  /** 1-based user round. Consecutive steps that share a latest user text share an index. */
  turn_index: number
  /** Short text of that user message. Null when the request has no user text. */
  turn_label: string | null
  cumulative_input_tokens: number
  cumulative_output_tokens: number
  cumulative_total_tokens: number
  cumulative_latency_ms: number
  flags: string[]
  request_preview: string
  waste_rules?: string[]
}

export interface WasteFinding {
  rule_id: string
  severity: 'info' | 'warn'
  request_ids: number[]
  message: string
  tokens_involved: number | null
}

export interface SessionDetail extends SessionSummary {
  slow_latency_ms: number
  steps: SessionStep[]
  findings?: WasteFinding[]
  finding_counts?: Record<string, number>
  flagged_request_ids?: number[]
}

export interface SessionsResponse {
  data: SessionSummary[]
  total: number
  offset: number
  limit: number
  has_more: boolean
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
