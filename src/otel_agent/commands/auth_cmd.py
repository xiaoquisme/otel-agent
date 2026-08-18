"""otel-agent auth — SuperGrok login and optional Hermes/Grok import."""
from __future__ import annotations

import json
import webbrowser
from pathlib import Path

import httpx

from otel_agent.auth_vault import (
    AuthError,
    DEFAULT_XAI_BASE_URL,
    extract_hermes_xai_grant,
    get_status,
    save_grant,
)
from otel_agent.config import AUTH_XAI_OAUTH, upsert_provider
from otel_agent.xai_oauth import (
    fetch_discovery,
    is_remote_session,
    poll_device_token,
    request_device_code,
)

HERMES_AUTH = Path.home() / ".hermes" / "auth.json"
GROK_AUTH = Path.home() / ".grok" / "auth.json"
DEFAULT_PROVIDER = "xai"


def handle_auth(args) -> None:
    action = getattr(args, "auth_action", None) or "status"
    if action == "login":
        _login(args)
    elif action == "import-xai":
        _import_xai(args)
    else:
        _status(args)


def _status(args) -> None:
    status = get_status(DEFAULT_PROVIDER)
    if status["logged_in"]:
        source = status.get("imported_from") or "vault"
        print(f"xAI OAuth  logged in  (from {source})")
        print(f"  vault: {status['path']}")
    else:
        print("xAI OAuth  not logged in")
        print("  Run: otel-agent auth login")
        print("  Or:  otel-agent auth import-xai   (if Hermes / Grok CLI already signed in)")


def _upsert_xai_provider(config_path: Path) -> None:
    upsert_provider(
        config_path,
        {
            "name": DEFAULT_PROVIDER,
            "base_url": DEFAULT_XAI_BASE_URL,
            "auth": AUTH_XAI_OAUTH,
            "api_format": "openai",
        },
    )


def _login(args) -> None:
    config_path = Path(getattr(args, "config", "~/.otel-agent/config.yaml")).expanduser()
    open_browser = not getattr(args, "no_browser", False)
    if is_remote_session():
        open_browser = False

    print("Signing in to xAI Grok (SuperGrok)...")
    print("Tokens stay in ~/.otel-agent/auth.json.")
    try:
        with httpx.Client(timeout=20.0, headers={"Accept": "application/json"}) as client:
            discovery = fetch_discovery(client)
            device = request_device_code(client)
            verification_url = str(
                device.get("verification_uri_complete") or device["verification_uri"]
            )
            user_code = str(device["user_code"])
            print()
            print("To continue:")
            print(f"  1. Open: {verification_url}")
            print(f"  2. If prompted, enter code: {user_code}")
            if open_browser:
                try:
                    opened = webbrowser.open(verification_url)
                except Exception:
                    opened = False
                if opened:
                    print("  (Opened browser for verification)")
                else:
                    print("  Could not open browser automatically — use the URL above.")
            print()
            print("Waiting for authorization...")
            tokens = poll_device_token(
                client,
                token_endpoint=str(discovery.get("token_endpoint") or "https://auth.x.ai/oauth2/token"),
                device_code=str(device["device_code"]),
                expires_in=int(device["expires_in"]),
                poll_interval=int(device["interval"]),
            )
    except AuthError as exc:
        print(f"Login failed: {exc}")
        raise SystemExit(1) from exc
    except httpx.HTTPError as exc:
        print(f"Login failed: {exc}")
        raise SystemExit(1) from exc

    save_grant(DEFAULT_PROVIDER, tokens, discovery=discovery, imported_from="device-code")
    _upsert_xai_provider(config_path)
    print()
    print("Login successful.")
    print(f"  provider: {DEFAULT_PROVIDER}  (use model xai/grok-4.6)")
    print(f"  config:   {config_path}")


def _import_xai(args) -> None:
    config_path = Path(getattr(args, "config", "~/.otel-agent/config.yaml")).expanduser()
    candidates = [HERMES_AUTH, GROK_AUTH]
    last_error = "No Hermes or Grok auth file found. Use: otel-agent auth login"
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
        _upsert_xai_provider(config_path)
        print(f"Imported SuperGrok grant from {source}")
        print(f"  provider: {DEFAULT_PROVIDER}  (use model xai/grok-4.6)")
        print(f"  config:   {config_path}")
        print("  Tokens stay in ~/.otel-agent/auth.json — Hermes auth.json was not modified.")
        return
    print(f"Import failed: {last_error}")
    raise SystemExit(1)
