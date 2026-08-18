"""RFC 8628 device-code login against xAI (same public client as Hermes/Grok)."""
from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from typing import Any

import httpx

from otel_agent.auth_vault import (
    AuthError,
    XAI_OAUTH_CLIENT_ID,
    XAI_OAUTH_DISCOVERY_URL,
)

XAI_OAUTH_DEVICE_CODE_URL = "https://auth.x.ai/oauth2/device/code"
XAI_OAUTH_SCOPE = "openid profile email offline_access grok-cli:access api:access"
XAI_OAUTH_TOKEN_URL = "https://auth.x.ai/oauth2/token"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

SleepFn = Callable[[float], None]
MonoFn = Callable[[], float]


def is_remote_session() -> bool:
    """True when a graphical browser is unlikely to reach the operator."""
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return True
    if (
        sys.platform.startswith("linux")
        and not os.environ.get("DISPLAY")
        and not os.environ.get("WAYLAND_DISPLAY")
    ):
        return True
    return False


def fetch_discovery(client: httpx.Client) -> dict[str, Any]:
    resp = client.get(XAI_OAUTH_DISCOVERY_URL)
    if resp.status_code != 200:
        return {"token_endpoint": XAI_OAUTH_TOKEN_URL}
    try:
        payload = resp.json()
    except Exception:
        return {"token_endpoint": XAI_OAUTH_TOKEN_URL}
    if not isinstance(payload, dict):
        return {"token_endpoint": XAI_OAUTH_TOKEN_URL}
    endpoint = str(payload.get("token_endpoint") or "").strip() or XAI_OAUTH_TOKEN_URL
    payload["token_endpoint"] = endpoint
    return payload


def request_device_code(client: httpx.Client) -> dict[str, Any]:
    resp = client.post(
        XAI_OAUTH_DEVICE_CODE_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        data={"client_id": XAI_OAUTH_CLIENT_ID, "scope": XAI_OAUTH_SCOPE},
    )
    if resp.status_code != 200:
        raise AuthError(
            f"xAI device-code request failed (HTTP {resp.status_code})."
            + (f" {resp.text.strip()}" if resp.text else "")
        )
    payload = resp.json()
    required = (
        "device_code",
        "user_code",
        "verification_uri",
        "verification_uri_complete",
        "expires_in",
        "interval",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        raise AuthError(f"xAI device-code response missing fields: {', '.join(missing)}")
    return payload


def poll_device_token(
    client: httpx.Client,
    *,
    token_endpoint: str,
    device_code: str,
    expires_in: int,
    poll_interval: int,
    sleep: SleepFn = time.sleep,
    monotonic: MonoFn = time.monotonic,
) -> dict[str, Any]:
    deadline = monotonic() + max(1, int(expires_in))
    current_interval = max(1, int(poll_interval))
    while monotonic() < deadline:
        resp = client.post(
            token_endpoint,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={
                "grant_type": DEVICE_GRANT,
                "client_id": XAI_OAUTH_CLIENT_ID,
                "device_code": device_code,
            },
        )
        if resp.status_code == 200:
            payload = resp.json()
            if not str(payload.get("access_token") or "").strip():
                raise AuthError("xAI device-code token response did not include an access_token.")
            if not str(payload.get("refresh_token") or "").strip():
                raise AuthError("xAI device-code token response did not include a refresh_token.")
            return payload
        try:
            error_payload = resp.json()
        except Exception:
            raise AuthError(
                f"xAI device-code token polling failed (HTTP {resp.status_code})."
            ) from None
        error_code = str(error_payload.get("error") or "")
        if error_code == "authorization_pending":
            sleep(current_interval)
            continue
        if error_code == "slow_down":
            current_interval = min(current_interval + 1, 30)
            sleep(current_interval)
            continue
        description = (
            error_payload.get("error_description")
            or error_payload.get("error")
            or resp.text
        )
        raise AuthError(f"xAI device-code token polling failed: {description}")
    raise AuthError("Timed out waiting for xAI device authorization.")
