"""Tests for CLI arg parsing (backward compat with test_proxy.py name)."""

from otel_agent.cli import build_parser


def test_parser_defaults():
    parser = build_parser()
    args = parser.parse_args(["proxy"])
    assert args.port == 8080
    assert args.upstream == ""
    assert args.db == "~/.otel-agent/telemetry.db"


def test_parser_custom_values():
    parser = build_parser()
    args = parser.parse_args([
        "proxy", "--port", "9090",
        "--upstream", "https://api.anthropic.com",
        "--db", "/tmp/logs.db",
    ])
    assert args.port == 9090
    assert args.upstream == "https://api.anthropic.com"
    assert args.db == "/tmp/logs.db"


def test_parser_view_subcommand():
    parser = build_parser()
    args = parser.parse_args(["view", "--filter", "openai", "--limit", "50"])
    assert args.command == "view"
    assert args.filter == "openai"
    assert args.limit == 50


def test_parser_init_subcommand():
    parser = build_parser()
    args = parser.parse_args(["init", "--config", "/tmp/test.yaml"])
    assert args.command == "init"
    assert args.config == "/tmp/test.yaml"
