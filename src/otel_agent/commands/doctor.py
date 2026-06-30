"otel-agent doctor subcommand."

import socket
import sys
from pathlib import Path

from otel_agent.config import Config


def handle_doctor(args) -> None:
    "Check installation health."
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

    # mitmproxy
    try:
        import mitmproxy
        ver = getattr(mitmproxy, '__version__', 'unknown')
        print(f"  mitmproxy {ver}  ✅")
    except ImportError:
        all_ok = False
        print("  mitmproxy  ❌")
        print("    → Install: uv sync")

    # Config
    config_path = Path(getattr(args, 'config', '~/.otel-agent/config.yaml')).expanduser()
    if config_path.exists():
        try:
            config = Config(config_path)
            print("  Config valid  ✅")
            routes = config.routes
            if routes:
                print("  Active routes:")
                for route in routes:
                    print(f"    {route['prefix']:<12} {route['provider']:<16} {route['base_url']}")
            else:
                print("  No active routes configured")
        except Exception as e:
            all_ok = False
            print(f"  Config invalid  ❌")
            print(f"    → {e}")
    else:
        print(f"  Config missing  ⚠️")
        print(f"    → Run: otel-agent init")

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
