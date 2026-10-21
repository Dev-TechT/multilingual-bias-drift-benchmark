from __future__ import annotations

import argparse
import os
import threading
import webbrowser


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the Multilingual Bias Drift Benchmark web app.")
    parser.add_argument("--host", default=os.environ.get("MBDB_HOST", "127.0.0.1"), help="Bind address (default 127.0.0.1; use 0.0.0.0 only behind auth/reverse proxy)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MBDB_PORT", "8000")))
    parser.add_argument("--open", action="store_true", help="Open the browser after start")
    parser.add_argument("--reload", action="store_true", help="Auto-reload for development")
    args = parser.parse_args(argv)
    os.environ.setdefault("MBDB_DEMO_DELAY_SECONDS", "0.15")  # makes the mock-drift demo watchable live
    try:
        import uvicorn
    except ImportError:  # pragma: no cover
        print("The web app needs the 'web' extra: pip install -e .[web]")
        return 1
    url = f"http://{'127.0.0.1' if args.host in {'0.0.0.0', '::'} else args.host}:{args.port}"
    print(f"Multilingual Bias Drift Benchmark: {url}  (Ctrl+C to stop)")
    if args.open:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("fillblank_web.app:app", host=args.host, port=args.port, reload=args.reload, proxy_headers=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
