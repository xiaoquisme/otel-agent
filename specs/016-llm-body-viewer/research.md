# Research: LLM-Aware Body Viewer

**Date**: 2026-07-09
**Feature**: 016-llm-body-viewer

## Decision 1: Markdown Rendering Library

**Decision**: marked.js via CDN

**Rationale**: marked.js (~25KB) is the most widely used client-side markdown renderer. GitHub, Stack Overflow, and countless projects use it. Zero dependencies, CDN-hosted, handles all standard markdown (headings, code blocks, lists, bold/italic, tables). For a single-file dashboard this is the clear choice.

**Alternatives considered**:
- markdown-it (~30KB): More extensible plugin system, but we don't need plugins. Slightly heavier.
- showdown (~30KB): Older, less actively maintained than marked.js.
- unified/remark (~50KB): AST-based, powerful but overkill for our use case.
- snarkdown (~1KB): Too minimal — doesn't support code blocks, which LLM outputs frequently contain.
- Custom parser: Would need ~200+ lines to handle markdown properly. Not worth reinventing.

## Decision 2: XSS Sanitization

**Decision**: DOMPurify via CDN

**Rationale**: DOMPurify (~7KB) is the industry standard for HTML sanitization. Used by Wikipedia, Google, and major security-conscious projects. Since we're rendering user-controlled content (LLM responses) as HTML via marked.js, sanitization is mandatory.

**Alternatives considered**:
- marked.js built-in sanitization: Deprecated and removed in recent versions. Not reliable.
- Custom regex-based sanitization: Incomplete, easy to miss edge cases. Security risk.
- sanitize-html (~10KB): Good but less battle-tested than DOMPurify.

## Decision 3: OpenAI Format Detection

**Decision**: Check for `messages` array + `model` field in request; `choices` array in response.

**Rationale**: OpenAI chat completion format always has `model` + `messages` in requests and `choices` in responses. This is stable across API versions.

**OpenAI Request detection**:
```javascript
parsed.messages && Array.isArray(parsed.messages) && parsed.model
```

**OpenAI Response detection**:
```javascript
parsed.choices && Array.isArray(parsed.choices)
```

## Decision 4: Anthropic Format Detection

**Decision**: Check for `messages` array + `max_tokens` in request; `content` array in response.

**Rationale**: Anthropic messages API always has `max_tokens` in requests (required field) and `content` array in responses.

**Anthropic Request detection**:
```javascript
parsed.messages && Array.isArray(parsed.messages) && parsed.max_tokens !== undefined
```

**Anthropic Response detection**:
```javascript
parsed.content && Array.isArray(parsed.content) && parsed.type === 'message'
```

## Decision 5: Chat UI Layout

**Decision**: Chat-bubble style with role labels, using CSS flexbox. No external UI framework.

**Rationale**: A simple chat-bubble layout (system=full-width muted, user=right-aligned, assistant=left-aligned) is ~50 lines of CSS. No need for React/Vue/component library. Consistent with the existing single-file approach.

**Layout pattern** (inspired by Langfuse/LobeChat):
- Each message in a `<div class="chat-message">` with role-specific class
- Role label as a small badge above or beside the content
- Content rendered as markdown via marked.js + DOMPurify
- System messages: full-width, muted background, smaller font
- User messages: slightly different background, left-aligned
- Assistant messages: slightly different background, left-aligned (or right for contrast)

## Decision 6: Raw JSON Toggle

**Decision**: "Show Raw" / "Show Formatted" toggle button in body viewer.

**Rationale**: Per spec clarification — LLM view is default, toggle provides access to raw JSON. Per-request toggle state (no global state).

**Implementation**: Two containers (`.body-llm` and `.body-raw`), toggle button switches `display` between them. Raw container uses existing `highlightJsonString`.

## Decision 7: Anthropic Content Block Handling

**Decision**: Extract text blocks, render as markdown. Non-text blocks show placeholder.

**Rationale**: Anthropic content can be `[{type: "text", text: "..."}, {type: "image", source: {...}}]`. We render text blocks with marked.js and show "[Image content]" placeholder for image blocks. Tool use blocks show "[Tool use: {name}]".
