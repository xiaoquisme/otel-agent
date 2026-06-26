# Data Model: Path-Based Routing

**Feature**: 002-path-based-routing
**Date**: 2026-06-26

## Entities

### ProviderConfig (extended)

| Field     | Type         | Required | Default             | Description                         |
| --------- | ------------ | -------- | ------------------- | ----------------------------------- |
| name      | string       | yes      | (from YAML key)     | Provider identifier                 |
| type      | string       | no       | inferred from name  | API style: `openai` or `anthropic`  |
| prefix    | string       | no       | `/<name>`           | URL path prefix for routing         |
| base_url  | string       | yes      | —                   | Upstream API base URL               |
| keys      | list[KeyEntry] | yes    | —                   | API keys with active flag           |

**Type inference rules**:
- If `name` contains "anthropic" → `type: anthropic`
- Otherwise → `type: openai`

**Prefix inference rules**:
- If `prefix` not set → `/<name>` (e.g., provider `openai` → `/openai`)
- Prefix MUST start with `/` and MUST NOT end with `/`

### Route (derived, not stored)

| Field       | Type   | Description                              |
| ----------- | ------ | ---------------------------------------- |
| prefix      | string | URL path prefix (e.g., `/openai`)        |
| provider    | string | Provider name                            |
| type        | string | API style (determines auth header)       |
| base_url    | string | Upstream URL                             |

**Derived at config load time.** The `Config` class builds a route table from provider configs.

### KeyEntry (unchanged)

| Field  | Type    | Default | Description          |
| ------ | ------- | ------- | -------------------- |
| key    | string  | —       | API key value        |
| active | boolean | true    | Whether key is active|

## Validation Rules

1. Prefix MUST start with `/` — reject otherwise
2. Prefix MUST NOT end with `/` — reject otherwise
3. Prefixes MUST be unique across all providers — reject duplicates
4. `type` MUST be `openai` or `anthropic` — reject otherwise
5. `base_url` MUST NOT be empty — reject otherwise
6. At least one provider MUST have at least one active key — warn otherwise

## Config Example

```yaml
default_provider: openai

providers:
  openai:
    type: openai
    prefix: /openai
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-proj-xxx
        active: true

  anthropic:
    type: anthropic
    prefix: /anthropic
    base_url: https://api.anthropic.com
    keys:
      - key: sk-ant-xxx
        active: true

  deepseek:
    type: openai
    prefix: /deepseek
    base_url: https://api.deepseek.com/v1
    keys:
      - key: sk-ds-xxx
        active: true
```
