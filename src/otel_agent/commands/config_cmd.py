"""otel-agent config subcommand."""

import os
import re
import subprocess
import sys
from pathlib import Path


def handle_config(args) -> None:
    """Handle config path|show|edit subcommands."""
    config_path = Path(args.config).expanduser()

    if args.config_action == "path":
        print(config_path)

    elif args.config_action == "show":
        if not config_path.exists():
            print(f"Config not found: {config_path}")
            print("Run: otel-agent init")
            sys.exit(1)
        content = config_path.read_text()
        masked = _mask_keys(content)
        print(masked)

    elif args.config_action == "edit":
        editor = os.environ.get("EDITOR", "vim")
        if not config_path.exists():
            print(f"Config not found: {config_path}")
            print("Run: otel-agent init first")
            sys.exit(1)
        subprocess.run([editor, str(config_path)])

    else:
        print("Usage: otel-agent config [path|show|edit]")
        sys.exit(1)


def _mask_keys(content: str) -> str:
    """Mask API key values in YAML content."""
    return re.sub(
        r'(key:\s*)(\S+)',
        lambda m: m.group(1) + m.group(2)[:6] + '***' if len(m.group(2)) > 6 else m.group(1) + '***',
        content,
    )
