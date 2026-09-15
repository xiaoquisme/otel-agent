"""otel-agent auth — SuperGrok login and grant adoption from sibling CLIs."""
from __future__ import annotations

import webbrowser
from pathlib import Path

import httpx

from otel_agent.auth_vault import (
    AuthError,
    DEFAULT_CODEX_BASE_URL,
    DEFAULT_XAI_BASE_URL,
    GrantSource,
    adopt_grant,
    get_status,
    read_grant_source,
    save_grant,
)
from otel_agent.codex_oauth import (
    CODEX_OAUTH_CLIENT_ID,
    CODEX_OAUTH_DEVICE_TOKEN_URL,
    CODEX_OAUTH_TOKEN_URL,
    CODEX_OAUTH_VERIFICATION_URL,
    exchange_authorization_code,
    poll_device_token as poll_codex_device_token,
    request_device_code as request_codex_device_code,
)
from otel_agent.config import AUTH_CODEX_OAUTH, AUTH_XAI_OAUTH, upsert_provider
from otel_agent.xai_oauth import (
    fetch_discovery,
    is_remote_session,
    poll_device_token,
    request_device_code,
)

HERMES_AUTH = Path.home() / ".hermes" / "auth.json"
GROK_AUTH = Path.home() / ".grok" / "auth.json"
DEFAULT_PROVIDER = "xai"
CODEX_PROVIDER = "codex"

#: Where each sibling CLI keeps a grant this gateway may adopt (D2). Adopting
#: is a lookup here rather than a per-vendor branch: the file, the pointers
#: into it, the provider the grant lands under and whatever the store cannot
#: supply are all declared as rows. The owner's file is read, never written.
GRANT_SOURCES: tuple[GrantSource, ...] = (
    GrantSource(
        label="hermes",
        path=HERMES_AUTH,
        # `providers` first: that is where xAI's discovery document — and so
        # the token endpoint its refresh must present — is recorded.
        pointers=(("providers", "xai-oauth"), ("credential_pool", "xai-oauth")),
        provider=DEFAULT_PROVIDER,
        auth=AUTH_XAI_OAUTH,
        base_url=DEFAULT_XAI_BASE_URL,
    ),
    GrantSource(
        label="grok-cli",
        path=GROK_AUTH,
        pointers=(("providers", "xai-oauth"), ("credential_pool", "xai-oauth")),
        provider=DEFAULT_PROVIDER,
        auth=AUTH_XAI_OAUTH,
        base_url=DEFAULT_XAI_BASE_URL,
    ),
    GrantSource(
        label="hermes",
        path=HERMES_AUTH,
        # `credential_pool` first: `base_url` and `source` live on the pool
        # entry. `providers["openai-codex"]` carries only
        # `tokens`/`last_refresh`/`auth_mode`.
        pointers=(("credential_pool", "openai-codex"), ("providers", "openai-codex")),
        provider=CODEX_PROVIDER,
        auth=AUTH_CODEX_OAUTH,
        base_url=DEFAULT_CODEX_BASE_URL,
        # token_endpoint and client_id stay empty on purpose: the store carries
        # neither (its base_url is the API host, not the token host), so both
        # are read off the adopted grant's own claims by adopt_grant().
    ),
)


def grant_sources(provider: str) -> tuple[GrantSource, ...]:
    """Every declared source for *provider*, in declaration order."""
    return tuple(source for source in GRANT_SOURCES if source.provider == provider)


def handle_auth(args) -> None:
    action = getattr(args, "auth_action", None) or "status"
    if action == "login":
        _login(args)
    elif action == "login-codex":
        _login_codex(args)
    elif action == "import-xai":
        _import_xai(args)
    elif action == "import-codex":
        _import_codex(args)
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

    save_grant(
        DEFAULT_PROVIDER,
        tokens,
        auth=AUTH_XAI_OAUTH,
        discovery=discovery,
        imported_from="device-code",
    )
    _upsert_xai_provider(config_path)
    print()
    print("Login successful.")
    print(f"  provider: {DEFAULT_PROVIDER}  (use model xai/grok-4.6)")
    print(f"  config:   {config_path}")


def _login_codex(args) -> None:
    """Mint a Codex chain this gateway owns outright.

    Deliberately not an adoption: no sibling CLI is read, so nothing Hermes
    holds is refreshed, consumed, or revoked. The cost is one device-code
    approval by the human; the benefit is a chain with exactly one writer.
    """
    config_path = Path(getattr(args, "config", "~/.otel-agent/config.yaml")).expanduser()
    open_browser = not getattr(args, "no_browser", False)
    if is_remote_session():
        open_browser = False

    print("Signing in to Codex (ChatGPT subscription)...")
    print("This mints a new grant chain for this gateway — no other CLI is touched.")
    print("Tokens stay in ~/.otel-agent/auth.json.")
    try:
        with httpx.Client(timeout=20.0, headers={"Accept": "application/json"}) as client:
            device = request_codex_device_code(client)
            user_code = str(device["user_code"])
            print()
            print("To continue:")
            print(f"  1. Open: {CODEX_OAUTH_VERIFICATION_URL}")
            print(f"  2. Enter code: {user_code}")
            if open_browser:
                try:
                    opened = webbrowser.open(CODEX_OAUTH_VERIFICATION_URL)
                except Exception:
                    opened = False
                if opened:
                    print("  (Opened browser for verification)")
                else:
                    print("  Could not open browser automatically — use the URL above.")
            print()
            print("Waiting for authorization...")
            challenge = poll_codex_device_token(
                client,
                token_endpoint=CODEX_OAUTH_DEVICE_TOKEN_URL,
                device_auth_id=str(device["device_auth_id"]),
                user_code=user_code,
                expires_in=int(device["expires_in"]),
                poll_interval=int(device["interval"]),
            )
            tokens = exchange_authorization_code(
                client,
                token_endpoint=CODEX_OAUTH_TOKEN_URL,
                authorization_code=str(challenge["authorization_code"]),
                code_verifier=str(challenge["code_verifier"]),
            )
    except AuthError as exc:
        print(f"Login failed: {exc}")
        raise SystemExit(1) from exc
    except httpx.HTTPError as exc:
        print(f"Login failed: {exc}")
        raise SystemExit(1) from exc

    save_grant(
        CODEX_PROVIDER,
        tokens,
        auth=AUTH_CODEX_OAUTH,
        discovery={"token_endpoint": CODEX_OAUTH_TOKEN_URL},
        client_id=CODEX_OAUTH_CLIENT_ID,
        imported_from="device-code",
    )
    _upsert_codex_provider(config_path, DEFAULT_CODEX_BASE_URL)
    print()
    print("Login successful.")
    print(f"  provider: {CODEX_PROVIDER}  (use model codex/gpt-5)")
    print(f"  config:   {config_path}")
    print("  This chain is this gateway's own — no sibling CLI was read or modified.")


def _import_xai(args) -> None:
    config_path = Path(getattr(args, "config", "~/.otel-agent/config.yaml")).expanduser()
    last_error = "No Hermes or Grok auth file found. Use: otel-agent auth login"
    for source in grant_sources(DEFAULT_PROVIDER):
        try:
            grant = read_grant_source(source)
        except AuthError as exc:
            last_error = str(exc)
            continue
        save_grant(
            source.provider,
            grant.tokens,
            auth=source.auth,
            discovery=grant.discovery,
            imported_from=source.label,
        )
        _upsert_xai_provider(config_path)
        print(f"Imported SuperGrok grant from {source.path}")
        print(f"  provider: {DEFAULT_PROVIDER}  (use model xai/grok-4.6)")
        print(f"  config:   {config_path}")
        print(f"  Tokens stay in ~/.otel-agent/auth.json — {source.path} was not modified.")
        return
    print(f"Import failed: {last_error}")
    raise SystemExit(1)


def _upsert_codex_provider(config_path: Path, base_url: str) -> None:
    upsert_provider(
        config_path,
        {
            "name": CODEX_PROVIDER,
            "base_url": base_url,
            "auth": AUTH_CODEX_OAUTH,
            "api_format": "openai",
        },
    )


def _import_codex(args) -> None:
    """Adopt a Codex grant and hand the chain over to this gateway (F1)."""
    config_path = Path(getattr(args, "config", "~/.otel-agent/config.yaml")).expanduser()
    last_error = "No sibling CLI holds a Codex grant on this machine."
    for source in grant_sources(CODEX_PROVIDER):
        try:
            adoption = adopt_grant(source)
        except AuthError as exc:
            last_error = str(exc)
            continue
        _upsert_codex_provider(config_path, adoption.base_url)
        print(f"Adopted the Codex grant from {source.path}")
        print(f"  provider: {CODEX_PROVIDER}  (use model codex/gpt-5)")
        print(f"  config:   {config_path}")
        print(f"  Tokens stay in ~/.otel-agent/auth.json — {source.path} was not modified.")
        print()
        print("Hand-off — this gateway now owns the grant:")
        print("  1. Stop using this subscription from that CLI, or point it at this gateway.")
        print("  2. Its own sign-in is stale from now on; it must sign in again if you keep using it.")
        print("  3. A second writer that refreshes this chain will invalidate it.")
        return
    print(f"Adoption failed: {last_error}")
    raise SystemExit(1)
