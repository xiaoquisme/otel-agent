"""otel-agent init subcommand."""

from pathlib import Path
from otel_agent.config import DEFAULT_CONFIG


def handle_init(args) -> None:
    """Create default config file."""
    config_path = Path(args.config).expanduser()
    if config_path.exists():
        print(f"Config already exists: {config_path}")
        print("Edit it manually or delete it to regenerate.")
    else:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(DEFAULT_CONFIG)
        print(f"Created config: {config_path}")
        print("Edit it to add your API keys.")
