"""otel-agent doctor subcommand."""

import socket
import sys
from pathlib import Path

from otel_agent.config import Config


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
                print(f"    {name:<16} {provider.api_format:<10} {provider.base_url}")
        except Exception as e:
            all_ok = False
            print("  Config invalid  ❌")
            print(f"    → {e}")
    else:
        print("  Config missing  ⚠️")
        print("    → Run: otel-agent init")

    # Port
    port = getattr(args, 'port', 8080)
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
