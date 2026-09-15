"""Codex device-code login (RFC 8628-shaped) against the ChatGPT auth host.

Mirrors ``xai_oauth``: a device-code request, a poll loop, and token exchange.
The difference is that this vendor's device flow returns an authorization code
rather than a token pair, so there is a fourth step — the code-for-token
exchange at the end.

What this buys over ``auth import-codex`` is an *independent* chain. Adoption
copies a sibling CLI's rotating refresh token and then refreshes first, which
consumes the sibling's copy and forces it to sign in again; presenting that
stale copy later revokes the whole grant family, this gateway's credential
included. A device-code login mints a chain of its own, so no sibling is read,
refreshed, or invalidated.

The public client id is the sibling's own. This is the same precedent the xAI
flow set: a public client id identifies the application, not the user, and the
device grant it authorizes is the human's.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import httpx

from otel_agent.auth_vault import AuthError

CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_OAUTH_DEVICE_CODE_URL = "https://auth.openai.com/api/accounts/deviceauth/usercode"
CODEX_OAUTH_DEVICE_TOKEN_URL = "https://auth.openai.com/api/accounts/deviceauth/token"
CODEX_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_OAUTH_VERIFICATION_URL = "https://auth.openai.com/codex/device"
CODEX_OAUTH_REDIRECT_URI = "https://auth.openai.com/deviceauth/callback"
CODEX_OAUTH_GRANT_TYPE = "authorization_code"

#: Fallback window for the operator to enter the code, for a usercode response
#: that carries no readable ``expires_at``. The host does send one — an absolute
#: instant roughly fifteen minutes out, which is what the poll loop runs on —
#: but a response without it must not leave the loop running unbounded or
#: failing outright, so the field is read first and this only ever backs it up.
CODEX_DEVICE_AUTH_WINDOW_SECONDS = 900

#: Ceiling for the ``slow_down`` backoff, as in the device grant RFC.
MAX_POLL_INTERVAL_SECONDS = 30

SleepFn = Callable[[float], None]
MonoFn = Callable[[], float]


def _as_positive_int(value: Any, *, default: int) -> int:
    """*value* as whole seconds, floored at 1 — the server sends strings.

    The interval is documented as a number but arrives as a string in practice
    (and may be absent or unparseable), so it is coerced rather than trusted:
    a poll loop that reads it as ``"5"`` and divides, or that treats ``"0"`` as
    a literal, busy-waits against the auth host.
    """
    try:
        seconds = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default
    return max(1, seconds)


def _seconds_until(expires_at: Any) -> int | None:
    """*expires_at* — an absolute ISO-8601 instant — as whole seconds from now.

    ``None`` when it cannot be read as one, which is what makes the caller fall
    back rather than crash. The host sends the field with a UTC offset; a value
    with no offset at all is ambiguous, and read in the wrong zone it would put
    the deadline hours out in either direction, so it counts as unreadable too
    rather than being guessed at.
    """
    text = str(expires_at or "").strip()
    if not text:
        return None
    if text[-1] in ("Z", "z"):
        # The "Z" form is only accepted by ``fromisoformat`` on 3.11+.
        text = f"{text[:-1]}+00:00"
    try:
        deadline = datetime.fromisoformat(text)
    except ValueError:
        return None
    if deadline.tzinfo is None:
        return None
    return int((deadline - datetime.now(timezone.utc)).total_seconds())


def request_device_code(client: httpx.Client) -> dict[str, Any]:
    """Ask for a user code (step 1) and return it already normalized.

    ``interval`` and ``expires_in`` are coerced here so both callers and the
    poll loop work in whole seconds regardless of how the host encoded them.
    ``expires_in`` is the window that remains of the response's own
    ``expires_at``, and is only the module constant's window for a response
    that omits that field or encodes it in a form this cannot read. The shape
    of the returned mapping is unchanged.
    """
    resp = client.post(
        CODEX_OAUTH_DEVICE_CODE_URL,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        json={"client_id": CODEX_OAUTH_CLIENT_ID},
    )
    if resp.status_code != 200:
        # A workspace that has device authorization switched off answers here,
        # usually 403/404. Say so plainly: the alternative is a poll loop that
        # spins for the full window before reporting nothing useful.
        raise AuthError(
            f"Codex device-code request failed (HTTP {resp.status_code})."
            " Device authorization may be disabled for this workspace."
            + (f" {resp.text.strip()}" if resp.text else "")
        )
    try:
        payload = resp.json()
    except Exception:
        raise AuthError("Codex device-code response was not JSON.") from None
    if not isinstance(payload, dict):
        raise AuthError("Codex device-code response was not a JSON object.")
    missing = [key for key in ("device_auth_id", "user_code") if not payload.get(key)]
    if missing:
        raise AuthError(f"Codex device-code response missing fields: {', '.join(missing)}")
    payload["interval"] = _as_positive_int(payload.get("interval"), default=1)
    # The host supplies the expiry itself, as an absolute instant, so the
    # window is derived from it instead of assumed: a local constant would
    # drift the moment the server changed its mind. A response that omits it,
    # or sends something unreadable, still gets a bounded window rather than
    # an unbounded poll.
    remaining = _seconds_until(payload.get("expires_at"))
    if remaining is not None:
        payload["expires_in"] = max(1, remaining)
    else:
        payload["expires_in"] = _as_positive_int(
            payload.get("expires_in"), default=CODEX_DEVICE_AUTH_WINDOW_SECONDS
        )
    return payload


def poll_device_token(
    client: httpx.Client,
    *,
    token_endpoint: str,
    device_auth_id: str,
    user_code: str,
    expires_in: int,
    poll_interval: int,
    sleep: SleepFn | None = None,
    monotonic: MonoFn | None = None,
) -> dict[str, Any]:
    """Poll until the human approves, and return the authorization code (step 3).

    The returned mapping is the exchange's *input*, not a credential:
    ``{"authorization_code", "code_verifier"}``.

    ``403`` and ``404`` mean the human has not finished yet. This host answers
    a pending poll that way rather than with the RFC's ``authorization_pending``
    error body, so treating them as failures would abort every login at the
    first poll. Both are handled, so either convention works.

    ``sleep`` and ``monotonic`` default to the real ones, resolved at call time
    rather than bound as default arguments, so a caller (or a test) that
    replaces ``time.sleep`` actually gets the replacement.
    """
    _sleep: SleepFn = sleep or time.sleep
    _monotonic: MonoFn = monotonic or time.monotonic
    deadline = _monotonic() + max(1, int(expires_in))
    current_interval = max(1, int(poll_interval))
    while _monotonic() < deadline:
        resp = client.post(
            token_endpoint,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json={"device_auth_id": device_auth_id, "user_code": user_code},
        )
        if resp.status_code in (403, 404):
            _sleep(current_interval)
            continue
        if resp.status_code == 200:
            try:
                payload = resp.json()
            except Exception:
                raise AuthError("Codex device-code token response was not JSON.") from None
            for key in ("authorization_code", "code_verifier"):
                if not str(payload.get(key) or "").strip():
                    raise AuthError(f"Codex device-code token response did not include {key}.")
            return payload
        try:
            error_payload = resp.json()
        except Exception:
            raise AuthError(
                f"Codex device-code polling failed (HTTP {resp.status_code})."
                + (f" {resp.text.strip()}" if resp.text else "")
            ) from None
        error_code = str(error_payload.get("error") or "")
        if error_code in ("authorization_pending", "slow_down"):
            if error_code == "slow_down":
                current_interval = min(current_interval + 1, MAX_POLL_INTERVAL_SECONDS)
            _sleep(current_interval)
            continue
        description = (
            error_payload.get("error_description")
            or error_payload.get("error")
            or resp.text
        )
        raise AuthError(f"Codex device-code polling failed: {description}")
    raise AuthError("Timed out waiting for Codex device authorization.")


def exchange_authorization_code(
    client: httpx.Client,
    *,
    token_endpoint: str,
    authorization_code: str,
    code_verifier: str,
) -> dict[str, Any]:
    """Trade the approved code for the token pair (step 4).

    The one form-encoded step of the flow, and the only request that carries
    the PKCE verifier the device flow handed back.
    """
    resp = client.post(
        token_endpoint,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        data={
            "grant_type": CODEX_OAUTH_GRANT_TYPE,
            "client_id": CODEX_OAUTH_CLIENT_ID,
            "code": authorization_code,
            "code_verifier": code_verifier,
            "redirect_uri": CODEX_OAUTH_REDIRECT_URI,
        },
    )
    if resp.status_code != 200:
        raise AuthError(
            f"Codex authorization-code exchange failed (HTTP {resp.status_code})."
            + (f" {resp.text.strip()}" if resp.text else "")
        )
    try:
        payload = resp.json()
    except Exception:
        raise AuthError("Codex token response was not JSON.") from None
    if not isinstance(payload, dict):
        raise AuthError("Codex token response was not a JSON object.")
    for key in ("access_token", "refresh_token"):
        if not str(payload.get(key) or "").strip():
            raise AuthError(f"Codex token response did not include a {key}.")
    return payload
