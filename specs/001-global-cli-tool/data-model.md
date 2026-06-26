# Data Model: Global CLI Tool

**Feature**: 001-global-cli-tool
**Date**: 2026-06-26

## Entities

### Config (`~/.otel-agent/config.yaml`)

| Field    | Type   | Description                          |
| -------- | ------ | ------------------------------------ |
| providers | map   | Provider name → ProviderConfig       |

### ProviderConfig

| Field    | Type         | Description                        |
| -------- | ------------ | ---------------------------------- |
| base_url | string       | Upstream API base URL              |
| keys     | list[KeyEntry] | API keys with active flag        |

### KeyEntry

| Field  | Type    | Description                     |
| ------ | ------- | ------------------------------- |
| key    | string  | The API key value               |
| active | boolean | Whether this key is in rotation |

### RequestLog (SQLite: `telemetry.db`)

| Field            | Type    | Description                       |
| ---------------- | ------- | --------------------------------- |
| id               | integer | Auto-increment primary key        |
| timestamp        | string  | ISO 8601 UTC timestamp            |
| method           | string  | HTTP method (POST, GET, etc.)     |
| url              | string  | Full request URL                  |
| upstream         | string  | Resolved upstream URL             |
| request_headers  | string  | JSON-encoded request headers      |
| request_body     | string  | Full request body                 |
| response_status  | integer | HTTP response status code         |
| response_headers | string  | JSON-encoded response headers     |
| response_body    | string  | Full response body                |
| latency_ms       | float   | Request latency in milliseconds   |

### feature.json (`.specify/feature.json`)

| Field            | Type   | Description                       |
| ---------------- | ------ | --------------------------------- |
| feature_directory | string | Path to current feature spec dir |

## Relationships

- Config contains N Providers
- Each Provider contains N KeyEntries
- RequestLog records are independent (no foreign keys)
- feature.json points to one spec directory

## Validation Rules

- Config: YAML must parse without errors. Provider names must be lowercase alphanumeric.
- KeyEntry: `key` must be non-empty string. `active` defaults to `true` if omitted.
- RequestLog: `method` must be valid HTTP verb. `latency_ms` must be non-negative.
