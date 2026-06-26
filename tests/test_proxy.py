import os
from otel_agent.proxy import build_parser, parse_api_keys


def test_parser_defaults():
    parser = build_parser()
    args = parser.parse_args(["proxy"])
    assert args.port == 8080
    assert args.upstream == ""
    assert args.db == "telemetry.db"


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


def test_parser_short_flags():
    parser = build_parser()
    args = parser.parse_args(["proxy", "-p", "3128", "-u", "https://localhost:8888"])
    assert args.port == 3128
    assert args.upstream == "https://localhost:8888"


def test_parser_view_subcommand():
    parser = build_parser()
    args = parser.parse_args(["view", "--filter", "openai", "--limit", "50"])
    assert args.command == "view"
    assert args.filter == "openai"
    assert args.limit == 50


def test_parser_api_key():
    parser = build_parser()
    args = parser.parse_args([
        "proxy",
        "-k", "openai.com:sk-test",
        "-k", "anthropic.com:sk-ant-test",
    ])
    assert args.api_key == ["openai.com:sk-test", "anthropic.com:sk-ant-test"]


def test_parse_api_keys_from_cli():
    keys = parse_api_keys(["openai.com:sk-xxx", "anthropic.com:sk-ant-yyy"], "")
    assert keys == {"openai.com": "sk-xxx", "anthropic.com": "sk-ant-yyy"}


def test_parse_api_keys_from_env(monkeypatch):
    monkeypatch.setenv("OTEL_API_KEYS", "openai.com:sk-env,anthropic.com:sk-ant-env")
    keys = parse_api_keys([], "")
    assert keys == {"openai.com": "sk-env", "anthropic.com": "sk-ant-env"}


def test_parse_api_keys_cli_overrides_env(monkeypatch):
    monkeypatch.setenv("OTEL_API_KEYS", "openai.com:sk-env")
    keys = parse_api_keys(["openai.com:sk-cli"], "")
    assert keys == {"openai.com": "sk-cli"}


def test_parse_api_keys_from_file(tmp_path):
    key_file = tmp_path / "keys.txt"
    key_file.write_text(
        "# comment\n"
        "openai.com:sk-file\n"
        "anthropic.com:sk-ant-file\n"
    )
    keys = parse_api_keys([], str(key_file))
    assert keys == {"openai.com": "sk-file", "anthropic.com": "sk-ant-file"}
