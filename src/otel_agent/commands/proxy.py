"""otel-agent proxy subcommand."""

import asyncio
from pathlib import Path


def handle_proxy(args) -> None:
    """Start the MITM proxy."""
    asyncio.run(_run_proxy(args))


async def _run_proxy(args) -> None:
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
    print(f"otel-agent proxy listening on :{args.port}{upstream_msg}")
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
