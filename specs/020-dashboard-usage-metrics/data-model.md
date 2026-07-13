# Data Model: Dashboard Usage Metrics

## Request Record (extended)

The existing request record remains the source of truth for telemetry. This feature adds an analytics projection at write time; existing request/response payload fields remain unchanged.

| Field | Type | Required | Description | Validation |
|---|---|---:|---|---|
| `id` | integer | yes | Existing request identifier. | Existing primary-key behavior. |
| `timestamp` | UTC timestamp text | yes | Existing request completion time. | Must be comparable to requested UTC range bounds. |
| `response_status` | integer | yes | Existing upstream response status. | A record is completed for usage aggregation only when it is in the 2xx range. |
| `model_name` | text | no | Client-visible model identifier from the original request, including any provider prefix. | Empty or malformed identifiers are stored as null. |
| `input_tokens` | non-negative integer | no | Provider-reported input/prompt tokens. | Null when absent, malformed, negative, or non-integral. |
| `output_tokens` | non-negative integer | no | Provider-reported output/completion tokens. | Null when absent, malformed, negative, or non-integral. |
| `total_tokens` | non-negative integer | no | Provider-reported total tokens, or the sum of available input/output values when the provider does not send a total. | Null only when no usable component exists; never estimated from text. |

### Compatibility and migration

- Analytics fields are nullable so every pre-feature request remains readable.
- Existing rows are not backfilled. They appear in the coverage count when they are completed but lack usable token data.
- Schema initialization must be idempotent for both storage backends and must add indexes needed for date-range aggregation and model grouping.
- SQLite-to-DuckDB migration preserves the analytics fields when present and leaves them null for legacy source records.

## Usage Summary (derived, not persisted)

A usage summary is calculated for one explicit UTC interval.

| Field | Type | Description |
|---|---|---|
| `start` | UTC ISO-8601 instant | Inclusive interval boundary, generated from the viewer's local start of day. |
| `end` | UTC ISO-8601 instant | Exclusive interval boundary, generated from the next local start of day. |
| `total_tokens` | integer | Sum of `total_tokens` for eligible records. |
| `input_tokens` | integer | Sum of available `input_tokens` for eligible records. |
| `output_tokens` | integer | Sum of available `output_tokens` for eligible records. |
| `eligible_request_count` | integer | Completed requests in the interval with a usable `total_tokens` value. |
| `excluded_request_count` | integer | Completed requests in the interval without usable token data. |
| `models` | ordered collection | Model usage summaries, descending by total tokens. |

### Eligibility rules

1. A request belongs to the summary when `start <= timestamp < end`.
2. Only 2xx requests participate in usage or coverage counts.
3. A request is eligible when `total_tokens` is non-null and non-negative.
4. An ineligible completed request increases `excluded_request_count` exactly once.
5. Null token components are omitted from their component aggregate rather than treated as zero.

## Model Usage Summary (derived)

| Field | Type | Description |
|---|---|---|
| `model_name` | text | Exact stored model identifier; use the display label `Unknown model` only when this field is null. |
| `total_tokens` | integer | Sum of eligible `total_tokens` for this model in the interval. |
| `input_tokens` | integer | Sum of available input values for this model. |
| `output_tokens` | integer | Sum of available output values for this model. |
| `request_count` | integer | Number of eligible completed requests for this model. |

### Ordering and display rules

- Order by `total_tokens` descending, then by model name for deterministic ties.
- Do not merge model identifiers by case, provider, or aliases.
- The unknown-model group is distinct from excluded records: it contains eligible usage whose model identifier was unavailable.

## State transitions

```text
Telemetry request received
  -> upstream response completed (or stream finalized)
  -> model and provider usage normalized; streaming retains the latest valid usage chunk
  -> request record written with nullable analytics projection
  -> included in a requested usage summary when 2xx, in-range, and total_tokens is usable
  -> otherwise counted as excluded coverage when 2xx and in-range
```
