"""otel-agent doctor subcommand."""

import socket
import sys
import time
from datetime import datetime
from pathlib import Path

from otel_agent.config import Config


def _iso_utc(timestamp: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))


def _epoch_of(iso: str) -> float | None:
    """Read one of the ISO-8601 timestamps either store records, or None.

    Tolerant on purpose: these timestamps come from a file this gateway does
    not own, and an unreadable one is a reason to say nothing, not to fail
    the doctor.
    """
    text = (iso or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _warn_on_a_second_writer(provider: str, status: dict) -> None:
    """Report a sibling CLI that is still refreshing the same grant (R3).

    Adoption is meant to leave this gateway the only writer. On a single-use
    rotating chain a second writer that presents a spent refresh token takes
    the whole family down for both of them, so an owner store whose
    ``last_refresh`` is newer than ours is that failure already forming rather
    than a hint to be skipped. Most machines have no such store, which is why
    the reader yields nothing rather than an error.
    """
    from otel_agent.auth_vault import read_owner_last_refresh
    from otel_agent.commands.auth_cmd import grant_sources

    gateway_at = _epoch_of(str(status.get("last_refresh") or ""))
    if gateway_at is None:
        return
    for source in grant_sources(provider):
        owner_iso = read_owner_last_refresh(source)
        owner_at = _epoch_of(owner_iso)
        if owner_at is None or owner_at <= gateway_at:
            continue
        print(
            f"    → the {source.label} CLI refreshed this grant at {owner_iso} — "
            f"later than this gateway ({_iso_utc(gateway_at)}). A second writer is "
            f"still active on this machine, and a refresh that loses the race "
            f"revokes the whole token family for both of them. Sign the other CLI "
            f"out, then re-adopt: otel-agent auth import-codex"
        )


def handle_doctor(args) -> None:
    """Check installation health."""
    print("otel-agent doctor\n")
    all_ok = True

    # Python version
    v = sys.version_info
    ok = v >= (3, 10)
    status = "✅" if ok else "❌"
    print(f"  Python {v.major}.{v.minor}.{v.micro}  {status}")
    if not ok:
        all_ok = False
        print("    → Need Python >= 3.10")

    # FastAPI
    try:
        import fastapi
        ver = getattr(fastapi, '__version__', 'unknown')
        print(f"  fastapi {ver}  ✅")
    except ImportError:
        all_ok = False
        print("  fastapi  ❌")
        print("    → Install: uv sync")

    # uvicorn
    try:
        import uvicorn
        ver = getattr(uvicorn, '__version__', 'unknown')
        print(f"  uvicorn {ver}  ✅")
    except ImportError:
        all_ok = False
        print("  uvicorn  ❌")
        print("    → Install: uv sync")

    # httpx
    try:
        import httpx
        ver = getattr(httpx, '__version__', 'unknown')
        print(f"  httpx {ver}  ✅")
    except ImportError:
        all_ok = False
        print("  httpx  ❌")
        print("    → Install: uv sync")

    # Config
    config_path = Path(getattr(args, 'config', '~/.otel-agent/config.yaml')).expanduser()
    if config_path.exists():
        try:
            config = Config(config_path)
            providers = config.providers
            print(f"  Config valid  ✅ ({len(providers)} provider(s))")
            for name, provider in providers.items():
                extra = f"  auth={provider.auth}" if provider.auth else ""
                print(f"    {name:<16} {provider.api_format:<10} {provider.base_url}{extra}")
        except Exception as e:
            all_ok = False
            print("  Config invalid  ❌")
            print(f"    → {e}")
    else:
        print("  Config missing  ⚠️")
        print("    → Run: otel-agent init")

    from otel_agent.auth_vault import get_status
    from otel_agent.commands.auth_cmd import CODEX_PROVIDER

    xai = get_status("xai")
    if xai["logged_in"]:
        print(f"  xAI OAuth  ✅ logged in ({xai.get('imported_from') or 'vault'})")
    else:
        print("  xAI OAuth  — not logged in (otel-agent auth login)")

    # The subscription the gateway holds itself. Like the row above, a missing
    # login is a warning and never sets all_ok: a gateway that has not adopted
    # the subscription yet is a gateway, not a broken installation.
    codex = get_status(CODEX_PROVIDER)
    if codex["logged_in"]:
        print(f"  Codex OAuth  ✅ logged in ({codex.get('imported_from') or 'vault'})")
        if codex.get("plan"):
            print(f"    plan: {codex['plan']}")
        expires_at = codex.get("expires_at")
        if isinstance(expires_at, (int, float)) and expires_at > 0:
            print(f"    expires: {_iso_utc(expires_at)}")
        last = codex.get("last_result")
        if isinstance(last, dict):
            if last.get("ok"):
                state = "ok"
            else:
                state = f"failed: {last.get('detail') or 'no reason recorded'}"
            at = last.get("at")
            when = _iso_utc(at) if isinstance(at, (int, float)) else "unknown"
            print(f"    last refresh: {state} ({when})")
        else:
            print("    last refresh: never attempted by this gateway")
        if not codex["available"]:
            print("    → left mid-refresh by an earlier process; re-adopt it")
        _warn_on_a_second_writer(CODEX_PROVIDER, codex)
    else:
        print("  Codex OAuth  — not logged in (otel-agent auth import-codex)")

    # Port
    port = getattr(args, 'port', 45638)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', port))
            print(f"  Port {port}  ✅ available")
    except OSError:
        print(f"  Port {port}  ⚠️ in use")
        print(f"    → Try: otel-agent proxy -p 9090")

    print()
    if all_ok:
        print("All checks passed.")
    else:
        print("Some checks failed. Fix issues above.")
