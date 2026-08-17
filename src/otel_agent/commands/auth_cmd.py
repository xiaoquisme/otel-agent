"""otel-agent auth subcommand — import SuperGrok grants from Hermes / Grok CLI."""
from __future__ import annotations

import json
from pathlib import Path

from otel_agent.auth_vault import (
    DEFAULT_XAI_BASE_URL,
    extract_hermes_xai_grant,
    get_status,
    save_grant,
)
from otel_agent.config import AUTH_XAI_OAUTH, upsert_provider

HERMES_AUTH = Path.home() / ".hermes" / "auth.json"
GROK_AUTH = Path.home() / ".grok" / "auth.json"
DEFAULT_PROVIDER = "xai"


def handle_auth(args) -> None:
    action = getattr(args, "auth_action", None) or "status"
    if action == "import-xai":
        _import_xai(args)
    else:
        _status(args)


def _status(args) -> None:
    status = get_status(DEFAULT_PROVIDER)
    if status["logged_in"]:
        source = status.get("imported_from") or "vault"
        print(f"xAI OAuth  logged in  (imported from {source})")
        print(f"  vault: {status['path']}")
    else:
        print("xAI OAuth  not imported")
        print("  Run: otel-agent auth import-xai")


def _import_xai(args) -> None:
    config_path = Path(getattr(args, "config", "~/.otel-agent/config.yaml")).expanduser()
    candidates = [HERMES_AUTH, GROK_AUTH]
    last_error = "No Hermes or Grok auth file found."
    for source in candidates:
        if not source.exists():
            continue
        try:
            store = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            last_error = f"{source} is unreadable: {exc}"
            continue
        grant = extract_hermes_xai_grant(store)
        if grant is None:
            last_error = f"{source} has no xai-oauth grant."
            continue
        tokens, discovery = grant
        imported_from = "hermes" if source == HERMES_AUTH else "grok-cli"
        save_grant(DEFAULT_PROVIDER, tokens, discovery=discovery, imported_from=imported_from)
        upsert_provider(
            config_path,
            {
                "name": DEFAULT_PROVIDER,
                "base_url": DEFAULT_XAI_BASE_URL,
                "auth": AUTH_XAI_OAUTH,
                "api_format": "openai",
            },
        )
        print(f"Imported SuperGrok grant from {source}")
        print(f"  provider: {DEFAULT_PROVIDER}  (use model xai/grok-4.6)")
        print(f"  config:   {config_path}")
        print("  Tokens stay in ~/.otel-agent/auth.json — Hermes auth.json was not modified.")
        return
    print(f"Import failed: {last_error}")
    raise SystemExit(1)
