# Data Model: Multi-Provider Routing

**Feature**: 007-multi-provider-routing
**Date**: 2026-06-30

## Entities

### ProviderType

| Field    | Type   | Required | Default | Description                                   |
| -------- | ------ | -------- | ------- | --------------------------------------------- |
| name     | string | yes      | —       | Provider type category, such as `openai`      |
| entries  | list[ProviderEntry] | yes | — | Configured providers under this type |

**Rules**:
- Exactly one entry MUST have `active = true`.
- Zero active entries or multiple active entries is invalid.

### ProviderEntry

| Field    | Type   | Required | Default | Description                                     |
| -------- | ------ | -------- | ------- | ----------------------------------------------- |
| name     | string | yes      | —       | Human-readable provider name                    |
| base_url | string | yes      | —       | Upstream API base URL                           |
| api_key  | string | yes      | —       | API key for this provider                       |
| active   | bool   | yes      | false   | Whether this provider is active for its type    |

**Rules**:
- `base_url` MUST be non-empty.
- `api_key` MUST be non-empty.
- `active` MUST be a boolean.

### KeyEntry (retained for rotation)

| Field  | Type   | Default | Description                |
| ------ | ------ | ------- | -------------------------- |
| key    | string | —       | API key value              |
| active | bool   | true    | Whether key is active      |

**Note**: Key rotation remains available, but provider selection is now driven by `ProviderEntry.active`, not key `active`.

### ActiveProviderSelection (derived)

| Field     | Type   | Description                                       |
| --------- | ------ | ------------------------------------------------- |
| type      | string | Provider type                                     |
| provider  | string | Active provider name for the type                 |
| base_url  | string | Active provider's upstream base URL               |
| api_key   | string | Active provider's API key                         |

**Derived at config load time.** Used by routing and auth injection.

## Validation Rules

1. Each provider type MUST have exactly one active provider entry.
2. Provider entry `base_url` and `api_key` MUST NOT be empty.
3. Only provider types `openai` and `anthropic` are supported.
4. Path routing is limited to `/openai` and `/anthropic`; old host/prefix fallback is removed.
5. Hot reload MUST revalidate active-provider rules and reject invalid state.

## Config Example

```yaml
providers:
  openai:
    - name: xiaomi
      base_url: https://xxx.xxx/xxx
      api_key: xxxx
      active: true
    - name: deesseek
      base_url: https://xxx.xxx/xxx
      api_key: xxxx
      active: false

  anthropic:
    - name: xiaomi
      base_url: https://xxx.xxx/xxx
      api_key: xxxx
      active: false
    - name: deesseek
      base_url: https://xxx.xxx/xxx
      api_key: xxxx
      active: true
```
