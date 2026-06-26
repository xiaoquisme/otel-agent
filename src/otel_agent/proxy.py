import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="otel-proxy",
        description="LLM API telemetry proxy — intercept, log, redirect.",
    )
    sub = parser.add_subparsers(dest="command")

    # proxy command
    proxy_p = sub.add_parser("proxy", help="Run the proxy")
    proxy_p.add_argument("-p", "--port", type=int, default=8080,
                         help="Proxy listen port (default: 8080)")
    proxy_p.add_argument("-u", "--upstream", type=str, default="",
                         help="Override upstream target (overrides config base_url)")
    proxy_p.add_argument("-d", "--db", type=str, default="telemetry.db",
                         help="SQLite database path (default: telemetry.db)")
    proxy_p.add_argument("-c", "--config", type=str,
                         default="~/.otel-agent/config.yaml",
                         help="Config file path (default: ~/.otel-agent/config.yaml)")

    # view command
    view_p = sub.add_parser("view", help="View logged requests")
    view_p.add_argument("-d", "--db", type=str, default="telemetry.db",
                        help="SQLite database path")
    view_p.add_argument("-f", "--filter", type=str, default="",
                        help="Filter by upstream (substring match)")
    view_p.add_argument("-n", "--limit", type=int, default=20)

    # init command
    init_p = sub.add_parser("init", help="Create default config file")
    init_p.add_argument("-c", "--config", type=str,
                        default="~/.otel-agent/config.yaml",
                        help="Config file path")

    return parser


async def run_proxy(args):
    from mitmproxy.options import Options
    from mitmproxy.tools.dump import DumpMaster
    from otel_agent.addon import TelemetryAddon
    from otel_agent.config import Config
    from otel_agent.logger import TelemetryLogger
    from otel_agent.rotator import KeyRotator

    config_path = Path(args.config).expanduser()
    logger = TelemetryLogger(Path(args.db))
    config = Config(config_path)
    rotator = KeyRotator(config)
    addon = TelemetryAddon(
        logger, config, rotator,
        upstream_override=args.upstream,
    )

    opts = Options(listen_port=args.port)
    master = DumpMaster(opts)
    master.addons.add(addon)

    upstream_msg = f" -> {args.upstream}" if args.upstream else ""
    print(f"otel-proxy listening on :{args.port}{upstream_msg}")
    print(f"logging to {args.db}")
    print(f"config: {config_path}")

    for name, provider in config._providers.items():
        active = len(provider.active_keys())
        total = len(provider.keys)
        print(f"  provider: {name} ({active}/{total} keys active)")

    print("Ctrl+C to stop\n")

    try:
        await master.run()
    except KeyboardInterrupt:
        pass
    finally:
        master.shutdown()
        logger.close()


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "view":
        from otel_agent.viewer import query_requests, format_request
        rows = query_requests(Path(args.db), args.filter, args.limit)
        if not rows:
            print("No requests logged yet.")
        for r in rows:
            print(format_request(r))
    elif args.command == "init":
        from otel_agent.config import DEFAULT_CONFIG
        config_path = Path(args.config).expanduser()
        if config_path.exists():
            print(f"Config already exists: {config_path}")
            print("Edit it manually or delete it to regenerate.")
        else:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(DEFAULT_CONFIG)
            print(f"Created config: {config_path}")
            print("Edit it to add your API keys.")
    else:
        import asyncio
        asyncio.run(run_proxy(args))


if __name__ == "__main__":
    main()
