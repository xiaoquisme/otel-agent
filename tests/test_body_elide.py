"""Unit tests for structured elision of oversized telemetry bodies."""

from __future__ import annotations

import json

from otel_agent.body_elide import elide_body


def _messages_body(n: int, per: int) -> str:
    return json.dumps({
        "model": "gpt-4",
        "messages": [
            {"role": "user" if i % 2 else "system", "content": f"msg{i} " + "x" * per}
            for i in range(n)
        ],
    })


class TestPassthrough:
    def test_under_limit_untouched(self) -> None:
        body = '{"a": 1}'
        assert elide_body(body, 100) == body

    def test_at_limit_untouched(self) -> None:
        body = "x" * 100
        assert elide_body(body, 100) == body


class TestMessageElision:
    def test_middle_elided_head_and_tail_kept(self) -> None:
        body = _messages_body(30, 5000)
        out = elide_body(body, 40_000)
        assert len(out) <= 40_000
        parsed = json.loads(out)  # always valid JSON
        msgs = parsed["messages"]
        assert msgs[0]["content"].startswith("msg0 ")
        assert msgs[-1]["content"].startswith("msg29 ")
        markers = [m for m in msgs if m.get("role") == "omitted"]
        assert len(markers) == 1
        meta = markers[0]["_elided"]
        assert meta["omitted_messages"] == 30 - (len(msgs) - 1)
        assert meta["omitted_bytes"] > 0

    def test_marker_is_human_readable(self) -> None:
        body = _messages_body(30, 5000)
        out = elide_body(body, 40_000)
        marker = [m for m in json.loads(out)["messages"] if m.get("role") == "omitted"][0]
        assert "otel-agent elided" in marker["content"]
        assert "messages" in marker["content"]

    def test_responses_input_list_elided(self) -> None:
        body = json.dumps({
            "model": "gpt-5",
            "input": [
                {"type": "message", "role": "user",
                 "content": [{"type": "input_text", "text": "x" * 5000}]}
                for _ in range(30)
            ],
        })
        out = elide_body(body, 40_000)
        parsed = json.loads(out)
        assert any(isinstance(i, dict) and "_elided" in i for i in parsed["input"])
        assert parsed["input"][0]["content"][0]["text"].startswith("xxx")
        assert parsed["input"][-1]["content"][0]["text"].startswith("xxx")

    def test_two_message_list_never_drops_elements(self) -> None:
        """Arrays under 3 elements are not elided — strings shrink instead."""
        body = json.dumps({"messages": [
            {"role": "user", "content": "A" * 100_000},
            {"role": "assistant", "content": "B" * 100_000},
        ]})
        out = elide_body(body, 50_000)
        parsed = json.loads(out)
        assert len(parsed["messages"]) == 2
        assert not any("_elided" in m for m in parsed["messages"])


class TestMediaRedaction:
    def test_data_url_placeholder_keeps_all_messages(self) -> None:
        big = "A" * 300_000
        body = json.dumps({"messages": [
            {"role": "user", "content": f"data:image/png;base64,{big}"},
            {"role": "assistant", "content": "short answer"},
        ]})
        out = elide_body(body, 50_000)
        assert len(out) <= 50_000
        parsed = json.loads(out)
        assert len(parsed["messages"]) == 2
        assert "data:image/png;base64,[otel-agent elided 300000 bytes of media]" \
            == parsed["messages"][0]["content"]
        assert parsed["messages"][1]["content"] == "short answer"

    def test_anthropic_source_data_placeholder(self) -> None:
        body = json.dumps({"messages": [
            {"role": "user", "content": [{
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": "A" * 2000},
            }]},
        ]})
        out = elide_body(body, 1500)
        parsed = json.loads(out)
        assert parsed["messages"][0]["content"][0]["source"]["data"] \
            == "[otel-agent elided 2000 bytes of media]"


class TestStringShrinking:
    def test_single_huge_message_stays_valid_json(self) -> None:
        body = json.dumps({"messages": [{"role": "user", "content": "Z" * 500_000}]})
        out = elide_body(body, 50_000)
        assert len(out) <= 50_000
        parsed = json.loads(out)
        assert parsed["messages"][0]["role"] == "user"
        content = parsed["messages"][0]["content"]
        assert content.startswith("ZZZ")
        assert content.endswith("ZZZ")
        assert "otel-agent elided" in content


class TestTextElision:
    def test_non_json_keeps_head_and_tail(self) -> None:
        body = "A" * 50_000 + "MIDDLE" + "B" * 50_000
        out = elide_body(body, 1000)
        assert len(out) <= 1000
        assert out.startswith("AAA")
        assert out.endswith("BBB")
        assert "otel-agent elided" in out
        assert "MIDDLE" not in out
