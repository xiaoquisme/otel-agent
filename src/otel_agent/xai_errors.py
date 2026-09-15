"""Rewrite overloaded xAI SuperGrok 403 bodies for gateway clients."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from otel_agent.config import Provider, auth_source

USAGE_URL = "https://grok.com/?_s=usage"
HINT = (
    "X Premium+ does not include API access — only a standalone SuperGrok "
    f"subscription can call api.x.ai. Check usage at {USAGE_URL}"
)


def is_xai_provider(provider: Provider) -> bool:
    """True when this provider's declaration asks for the SuperGrok hint.

    The auth declaration decides; the host check stays as a fallback for an
    api.x.ai provider configured with a plain api_key.
    """
    source = auth_source(provider.auth)
    if source is not None and source.entitlement_hint:
        return True
    host = (urlparse(provider.base_url).hostname or "").lower()
    return host == "api.x.ai" or host.endswith(".x.ai")


def _is_entitlement(text: str) -> bool:
    lower = text.lower()
    return (
        "do not have an active grok subscription" in lower
        or ("out of available resources" in lower and "grok" in lower)
        or ("does not have permission" in lower and "grok" in lower)
    )


def rewrite_xai_error(status: int, body: Any) -> Any:
    """Append a SuperGrok entitlement hint when the 403 body matches."""
    if status != 403 or not isinstance(body, dict):
        return body
    parts = []
    for key in ("error", "message", "code"):
        value = body.get(key)
        if isinstance(value, dict):
            parts.append(str(value.get("message", "")))
        elif isinstance(value, str):
            parts.append(value)
    blob = " ".join(parts)
    if not _is_entitlement(blob):
        return body
    if HINT.lower() in blob.lower():
        return body
    out = dict(body)
    err = out.get("error")
    if isinstance(err, dict):
        msg = str(err.get("message") or "")
        patched = dict(err)
        patched["message"] = f"{msg} {HINT}".strip()
        out["error"] = patched
    elif isinstance(err, str):
        out["error"] = f"{err} {HINT}".strip()
    else:
        out["error"] = {"message": HINT, "type": "permission_error"}
    return out
