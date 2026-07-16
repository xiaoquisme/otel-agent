"""Heuristic task classifier — zero-cost complexity tiering.

Classifies incoming requests into complexity tiers using structural signals
from the request body. No LLM calls, no external APIs, <1ms latency.
"""
from __future__ import annotations

import re


# Tier constants
SIMPLE = "simple"
MEDIUM = "medium"
COMPLEX = "complex"
REASONING = "reasoning"

ALL_TIERS = (SIMPLE, MEDIUM, COMPLEX, REASONING)

# Reasoning keywords that suggest complex multi-step reasoning
REASONING_KEYWORDS = re.compile(
    r"\b(step by step|prove|derive|think through|chain of thought|"
    r"reasoning|analyze|explain why|show your work|proof|"
    r"mathematical|logical deduction|first principles)\b",
    re.IGNORECASE,
)

# Code indicators
CODE_BLOCK_PATTERN = re.compile(r"```")
TOOL_DEFINITIONS_PATTERN = re.compile(r'"tools"\s*:\s*\[|function_call|tool_use|tool_choice', re.IGNORECASE)

# Simple indicators — short Q&A patterns
SIMPLE_KEYWORDS = re.compile(
    r"^(what|who|when|where|is|are|can you|do you|how do I|define|translate|"
    r"what is|what are|tell me|give me|list|name)\b",
    re.IGNORECASE,
)


def _extract_text_content(content: str | list) -> str:
    """Extract text from message content (string or multi-part list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                parts.append(part["text"])
        return "".join(parts)
    return ""


def classify_task(messages: list[dict]) -> str:
    """Classify a request into a complexity tier.

    Uses a single pass over messages to collect all heuristic signals:
    token count, code blocks, tool definitions, reasoning keywords,
    and simple-query patterns.

    Args:
        messages: The messages array from the chat completion request.

    Returns:
        One of: "simple", "medium", "complex", "reasoning"
    """
    if not messages:
        return SIMPLE

    total_chars = 0
    has_code = False
    has_tools = False
    has_reasoning = False
    last_user_content = ""

    for msg in messages:
        content = msg.get("content", "")
        text = _extract_text_content(content)
        total_chars += len(text)

        if not has_code and CODE_BLOCK_PATTERN.search(text):
            has_code = True
        if not has_reasoning and REASONING_KEYWORDS.search(text):
            has_reasoning = True
        if msg.get("tools") or msg.get("tool_choice"):
            has_tools = True
        if not has_tools and TOOL_DEFINITIONS_PATTERN.search(text):
            has_tools = True

        if msg.get("role") == "user":
            last_user_content = text

    token_est = total_chars // 4
    message_count = len(messages)

    # Check simple-query pattern once (only needs last user message)
    is_simple = (
        message_count <= 3
        and len(last_user_content) < 200
        and bool(SIMPLE_KEYWORDS.match(last_user_content.strip()))
    ) if last_user_content else message_count == 0

    # Reasoning tier — highest priority signals
    if has_reasoning and token_est > 1000:
        return REASONING
    if has_reasoning and message_count > 4:
        return REASONING

    # Complex tier — code generation, tool use, long context
    if has_code:
        return COMPLEX
    if has_tools and message_count > 2:
        return COMPLEX
    if token_est > 4000:
        return COMPLEX

    # Medium tier — summarization, multi-turn, moderate complexity
    if message_count > 3:
        return MEDIUM
    if token_est > 1000:
        return MEDIUM
    if has_tools:
        return MEDIUM

    # Simple tier — short Q&A, single turn, small context
    if is_simple:
        return SIMPLE

    # Default: short messages are simple, longer ones are medium
    return SIMPLE if token_est < 500 else MEDIUM
