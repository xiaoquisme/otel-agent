"""Tests for the heuristic task classifier."""
from otel_agent.classifier import classify_task, SIMPLE, MEDIUM, COMPLEX, REASONING


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


class TestClassifyTask:
    def test_empty_messages(self):
        assert classify_task([]) == SIMPLE

    def test_short_qa(self):
        messages = [_msg("user", "What is 2+2?")]
        assert classify_task(messages) == SIMPLE

    def test_simple_definition(self):
        messages = [_msg("user", "Define recursion")]
        assert classify_task(messages) == SIMPLE

    def test_simple_translate(self):
        messages = [_msg("user", "Translate hello to Spanish")]
        assert classify_task(messages) == SIMPLE

    def test_medium_summarization(self):
        content = "Summarize this document. " + "word " * 800
        messages = [_msg("user", content)]
        assert classify_task(messages) in (MEDIUM, COMPLEX)

    def test_medium_multi_turn(self):
        messages = [_msg("user", "Hi")] * 5
        assert classify_task(messages) == MEDIUM

    def test_complex_code_generation(self):
        code = "def merge_sort(arr):\n    " + "pass\n    " * 100
        messages = [
            _msg("system", "You are a coding assistant"),
            _msg("user", f"Write a Python function to merge two sorted arrays\n```python\n{code}\n```"),
        ]
        assert classify_task(messages) in (COMPLEX, REASONING)

    def test_complex_with_tools(self):
        messages = [
            _msg("user", "Search for the latest news"),
        ]
        messages[0]["tools"] = [{"type": "function", "function": {"name": "search"}}]
        assert classify_task(messages) in (MEDIUM, COMPLEX)

    def test_reasoning_step_by_step(self):
        content = "Prove that the square root of 2 is irrational. Think step by step and show your work. " + "x " * 2000
        messages = [_msg("user", content)]
        assert classify_task(messages) in (COMPLEX, REASONING)

    def test_reasoning_with_long_context(self):
        content = "Analyze this data and prove the hypothesis. " + "x " * 5000
        messages = [_msg("user", content)]
        assert classify_task(messages) in (COMPLEX, REASONING)

    def test_long_context_triggers_complex(self):
        content = "Process this document. " + "word " * 4000
        messages = [_msg("user", content)]
        assert classify_task(messages) in (COMPLEX, REASONING)

    def test_code_block_in_user_message(self):
        messages = [_msg("user", "Fix this code:\n```python\ndef foo():\n    pass\n```")]
        assert classify_task(messages) in (MEDIUM, COMPLEX)
