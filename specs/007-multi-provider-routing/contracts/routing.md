# Routing Contract

**Feature**: 007-multi-provider-routing

## Request Surface

| Client Path              | Behavior                                   |
| ------------------------ | ------------------------------------------ |
| `/openai`                | Forward to active OpenAI provider           |
| `/openai/...`            | Forward to active OpenAI provider           |
| `/anthropic`             | Forward to active Anthropic provider        |
| `/anthropic/...`         | Forward to active Anthropic provider        |
| Other paths              | Not supported by this routing surface       |

## Auth Injection

| Provider Type | Auth Header | Value Format      |
| ------------- | ----------- | ----------------- |
| `openai`      | `Authorization` | `Bearer <api_key>` |
| `anthropic`   | `x-api-key`     | `<api_key>`        |

## Error Behavior

| Condition                          | Result                                    |
| ---------------------------------- | ----------------------------------------- |
| No active provider for a type      | Startup/runtime error stating the type    |
| Multiple active providers for a type | Startup/runtime error listing duplicates |
| Active provider URL unreachable    | Actionable provider-level connection error |
| Active provider returns error      | Forward upstream response as-is           |

## Visibility

| Command                 | Output                                  |
| ----------------------- | --------------------------------------- |
| `otel-agent routes`     | Active provider assignment per type     |
| `otel-agent doctor`     | Active-provider config validation       |
