import argparse
import os
import sys
from pathlib import Path


def parse_api_keys(args_keys: list[str], key_file: str) -> dict:
    """Parse api keys from CLI args, env var, and key file.

    Priority: --api-key CLI > --key-file > OTEL_API_KEYS env var.
    Returns: {host_pattern: api_key}
    """
    keys = {}

    # From env var: OTEL_API_KEYS="openai.com:sk-xxx,anthropic.com:sk-ant-xxx"
    env_keys = os.environ.get("OTEL_API_KEYS", "")
    if env_keys:
        for pair in env_keys.split(","):
            pair = pair.strip()
            if ":" in pair:
                host, key = pair.split(":", 1)
                keys[host.strip()] = key.strip()

    # From key file (one HOST:KEY per line)
    if key_file:
        path = Path(key_file)
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and ":" in line:
                    host, key = line.split(":", 1)
                    keys[host.strip()] = key.strip()

    # From CLI args (highest priority, overrides everything)
    for pair in args_keys:
        if ":" in pair:
            host, key = pair.split(":", 1)
            keys[host.strip()] = key.strip()

    return keys


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
                         help="Override upstream target, e.g. https://api.anthropic.com")
    proxy_p.add_argument("-d", "--db", type=str, default="telemetry.db",
                         help="SQLite database path (default: telemetry.db)")
    proxy_p.add_argument(
        "-k", "--api-key", action="append", default=[],
        metavar="HOST:KEY",
        help="Inject API key for host (repeatable). "
             "Examples: -k openai.com:sk-xxx -k anthropic.com:sk-ant-xxx. "
             "Also reads OTEL_API_KEYS env var (comma-separated HOST:KEY pairs).",
    )
    proxy_p.add_argument(
        "--key-file", type=str, default="",
        help="Read api keys from file (one HOST:KEY per line)",
    )

    # view command
    view_p = sub.add_parser("view", help="View logged requests")
    view_p.add_argument("-d", "--db", type=str, default="telemetry.db",
                        help="SQLite database path")
    view_p.add_argument("-f", "--filter", type=str, default="",
                        help="Filter by upstream (substring match)")
    view_p.add_argument("-n", "--limit", type=int, default=20)

    return parser


async def run_proxy(args):
    from mitmproxy.options import Options
    from mitmproxy.tools.dump import DumpMaster
    from otel_agent.addon import TelemetryAddon
    from otel_agent.logger import TelemetryLogger

    logger = TelemetryLogger(Path(args.db))
    api_keys = parse_api_keys(args.api_key, args.key_file)
    addon = TelemetryAddon(logger, upstream_override=args.upstream, api_keys=api_keys)

    opts = Options(listen_port=args.port)
    master = DumpMaster(opts)
    master.addons.add(addon)

    upstream_msg = f" -> {args.upstream}" if args.upstream else ""
    print(f"otel-proxy listening on :{args.port}{upstream_msg}")
    print(f"logging to {args.db}")
    if api_keys:
        for host in api_keys:
            masked = api_keys[host][:6] + "..." if len(api_keys[host]) > 6 else "***"
            print(f"  api-key: {host} = {masked}")
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
    else:
        import asyncio
        asyncio.run(run_proxy(args))


if __name__ == "__main__":
    main()
