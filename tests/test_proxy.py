from otel_agent.proxy import build_parser


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
