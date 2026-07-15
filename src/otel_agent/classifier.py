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


def _estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate from message content (chars / 4)."""
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            # Multi-part content (e.g., Anthropic format)
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    total_chars += len(part["text"])
    return total_chars // 4


def _has_code_blocks(messages: list[dict]) -> bool:
    """Check if messages contain code fences."""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and CODE_BLOCK_PATTERN.search(content):
            return True
    return False


def _has_tool_definitions(messages: list[dict]) -> bool:
    """Check if messages contain tool/function definitions."""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and TOOL_DEFINITIONS_PATTERN.search(content):
            return True
        # Check message-level tools field
        if msg.get("tools") or msg.get("tool_choice"):
            return True
    return False


def _has_reasoning_keywords(messages: list[dict]) -> bool:
    """Check if messages contain reasoning prompts."""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and REASONING_KEYWORDS.search(content):
            return True
    return False


def _is_simple_query(messages: list[dict]) -> bool:
    """Check if this is a short, simple query."""
    if len(messages) > 3:
        return False
    if not messages:
        return True
    # Check last user message
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) < 200:
                return bool(SIMPLE_KEYWORDS.match(content.strip()))
    return False


def classify_task(messages: list[dict]) -> str:
    """Classify a request into a complexity tier.

    Uses zero-cost heuristic signals: token count, code blocks,
    tool definitions, message count, and reasoning keywords.

    Args:
        messages: The messages array from the chat completion request.

    Returns:
        One of: "simple", "medium", "complex", "reasoning"
    """
    if not messages:
        return SIMPLE

    token_est = _estimate_tokens(messages)
    message_count = len(messages)
    has_code = _has_code_blocks(messages)
    has_tools = _has_tool_definitions(messages)
    has_reasoning = _has_reasoning_keywords(messages)
    is_simple = _is_simple_query(messages)

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
    if has_code or has_tools:
        return MEDIUM

    # Simple tier — short Q&A, single turn, small context
    if is_simple:
        return SIMPLE

    # Default: short messages are simple, longer ones are medium
    return SIMPLE if token_est < 500 else MEDIUM
