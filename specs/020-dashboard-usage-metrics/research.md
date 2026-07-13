# Research: Dashboard Usage Metrics

## Decision 1: Persist a small analytics projection with each telemetry record

**Decision**: Persist the recorded model identifier and normalized token fields with each request, rather than repeatedly parsing request and response bodies while rendering the dashboard.

**Rationale**:
- The current request table stores `request_body` and `response_body` as JSON text. The dashboard's detail view already recognizes OpenAI (`prompt_tokens`, `completion_tokens`) and Anthropic (`input_tokens`, `output_tokens`) usage shapes, but list queries do not expose either field.
- A daily aggregate across 100,000 records must meet the two-second success criterion. Indexed numeric columns let the storage layer aggregate without loading, parsing, and transmitting every response body.
- Capturing the client-visible model identifier at logging time preserves provider prefixes and avoids conflating identically named models from different providers.

**Alternatives considered**:
- Aggregate by parsing stored JSON at read time: no schema migration, but too slow and fragile at the specified scale; it also duplicates parsing rules between the dashboard and storage layers.
- Introduce a separate roll-up table: useful for long retention and multi-range analytics, but unnecessary for the initial current-day-only scope and adds write-path complexity.

## Decision 2: Normalize OpenAI and Anthropic usage during telemetry logging

**Decision**: Add a pure normalization helper in the telemetry boundary that accepts common provider response shapes and yields nullable input, output, and total token values. For streaming requests, retain the latest valid normalized usage while decoding upstream chunks and persist it when the stream is finalized.

**Rationale**:
- OpenAI-compatible responses conventionally report `usage.prompt_tokens`, `usage.completion_tokens`, and often `usage.total_tokens`; Anthropic responses report `usage.input_tokens` and `usage.output_tokens`.
- Response conversion already maps between these shapes before telemetry is logged. Normalizing the client-visible response produces one consistent stored representation.
- A missing or malformed value must remain null, not become zero. When no provider total exists, the aggregate total may be computed from the available non-negative components. When all components are unavailable, the record is excluded and counted as incomplete coverage.
- Streaming telemetry stores only a bounded preview of concatenated chunks. Usage must therefore be extracted during chunk iteration, rather than reconstructed from that preview after logging.

**Alternatives considered**:
- Estimate usage from text: rejected by FR-006 because tokenizers and provider accounting differ.
- Support only OpenAI fields: rejected because the gateway supports Anthropic-compatible traffic and conversion.
- Parse persisted streaming previews after logging: rejected because the preview is truncated and chunk-concatenated. Streams that do not deliver a valid usage event remain visible as excluded coverage.

## Decision 3: Read metrics through the proxy when it is active

**Decision**: Add a dashboard usage-summary query to the storage interface and expose it from the proxy's existing internal dashboard API; the standalone dashboard uses that route first and retains its established offline direct-read fallback.

**Rationale**:
- The constitution prohibits concurrent DuckDB file access across proxy and dashboard processes. Existing request reads already use the proxy internal API for this reason.
- Reusing the same routing behavior keeps metric reads from causing storage lock contention or disrupting telemetry writes.

**Alternatives considered**:
- Give the dashboard a second direct read-only DuckDB connection while the proxy is active: rejected by the constitution's DuckDB concurrency rule.
- Query the request-list endpoint and aggregate in the browser: rejected because pagination omits most rows and it does not scale.

## Decision 4: Let the browser define the viewer-local day and pass explicit UTC bounds

**Decision**: The browser calculates the start and end of its local calendar day and requests the usage summary for those two UTC instants. The server validates that the range is positive and at most 48 hours.

**Rationale**:
- Stored request timestamps are UTC. Explicit UTC boundaries precisely express the requirement that "today" follows the dashboard viewer's local calendar day, including daylight-saving changes.
- The server does not need to infer a timezone from its host, which could differ from a remote viewer.

**Alternatives considered**:
- Use the dashboard server's local date: simpler but violates the viewer-local assumption.
- Send only a date and timezone name: workable but requires timezone database behavior and additional parsing that is unnecessary for a one-day range.

## Decision 5: Use a compact observability overview, not a new charting dependency

**Decision**: Add a top-of-dashboard usage section with three summary cards (total, input, output), a clear coverage note, and a ranked model table with a proportional bar and text values. Use the existing dark theme, semantic HTML, and responsive CSS.

**Rationale**:
- The current dashboard is a single self-contained HTML file with a data table and existing Chart.js dependency. A card-and-table layout is more directly useful for current-day monitoring than a new visualization library or an additional time-series chart.
- The design direction follows the data-dense, dark observability patterns of Sentry/Linear/Kraken while staying consistent with the existing interface.
- Text labels, actual numeric values, table headers, and color-independent rank indicators satisfy the accessibility requirements.

**Alternatives considered**:
- A pie or donut chart: visually attractive but less precise for comparing models, especially when there are many low-volume models.
- A full Langfuse-style analytics page: broader than the requested current-day dashboard augmentation.

## Decision 6: Apply additive, idempotent schema upgrades to both storage backends

**Decision**: Both DuckDB and SQLite initialization paths add the analytics columns and required indexes to existing databases without rewriting historical request bodies. SQLite-to-DuckDB migration creates the target schema with the same analytics columns and preserves null values for historical records.

**Rationale**:
- Existing databases already have the `requests` table without usage columns. New columns must be available immediately after upgrade without data loss.
- Historical requests cannot reliably be backfilled when bodies are disabled, truncated, streaming previews, or malformed. Null analytics values correctly drive the incomplete-coverage indicator.

**Alternatives considered**:
- Destructive schema recreation: rejected because it loses telemetry history.
- Mandatory full historical body backfill: rejected because it is unreliable and delays startup without improving correctness.

## Resolved Technical Context

- Runtime: Python 3.10+ with FastAPI, DuckDB, optional SQLite backend, and a standalone HTML/JavaScript dashboard.
- Storage ownership: the proxy owns the active DuckDB connection; dashboard reads route through the proxy while it is reachable.
- Test strategy: deterministic pytest unit and API-route coverage; network-dependent integration tests remain explicitly marked and are not required for the standard non-integration gate.
- All technical unknowns are resolved.
