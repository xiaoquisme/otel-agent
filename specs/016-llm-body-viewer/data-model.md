# Data Model: LLM-Aware Body Viewer

**Date**: 2026-07-09
**Feature**: 016-llm-body-viewer

## Summary

No database or storage changes. This feature is entirely client-side rendering logic. The "data model" here defines the shape of parsed LLM API bodies that the dashboard JavaScript will detect and render.

## Parsed Request Body Shapes

### OpenAI Chat Completion Request
```javascript
{
  model: "gpt-4",
  messages: [
    { role: "system", content: "You are a helpful assistant." },
    { role: "user", content: "Hello!" },
    { role: "assistant", content: "Hi there!" }
  ],
  temperature: 0.7,
  max_tokens: 1000,
  stream: false,
  tools: [...]  // optional
}
```

**Detection**: `parsed.messages && Array.isArray(parsed.messages) && parsed.model`

### Anthropic Messages Request
```javascript
{
  model: "claude-sonnet-4-20250514",
  max_tokens: 1024,
  messages: [
    { role: "user", content: "Hello!" }
  ],
  system: "You are a helpful assistant.",  // optional, separate field
  stream: false
}
```

**Detection**: `parsed.messages && Array.isArray(parsed.messages) && parsed.max_tokens !== undefined`

## Parsed Response Body Shapes

### OpenAI Chat Completion Response
```javascript
{
  id: "chatcmpl-xxx",
  object: "chat.completion",
  model: "gpt-4",
  choices: [
    {
      index: 0,
      message: { role: "assistant", content: "Hello! How can I help?" },
      finish_reason: "stop"
    }
  ],
  usage: { prompt_tokens: 10, completion_tokens: 8, total_tokens: 18 }
}
```

**Detection**: `parsed.choices && Array.isArray(parsed.choices)`

**Content extraction**: `parsed.choices[0].message.content` (as markdown string)
**Metadata**: `parsed.model`, `parsed.choices[0].finish_reason`

### Anthropic Messages Response
```javascript
{
  id: "msg_xxx",
  type: "message",
  model: "claude-sonnet-4-20250514",
  content: [
    { type: "text", text: "Hello! How can I help?" }
  ],
  stop_reason: "end_turn",
  usage: { input_tokens: 10, output_tokens: 8 }
}
```

**Detection**: `parsed.content && Array.isArray(parsed.content) && parsed.type === 'message'`

**Content extraction**: Filter `content` blocks where `type === "text"`, join `.text` fields (as markdown string)
**Metadata**: `parsed.model`, `parsed.stop_reason`

## Content Block Types (Anthropic)

| Block Type | Rendering | Placeholder |
|------------|-----------|-------------|
| `{type: "text", text: "..."}` | Render as markdown | — |
| `{type: "image", ...}` | Show placeholder | `[Image content]` |
| `{type: "tool_use", ...}` | Show placeholder | `[Tool use: {name}]` |
| `{type: "tool_result", ...}` | Show as preformatted text | — |
| Other | Show as preformatted text | — |
