#!/usr/bin/env python3
"""Serve a generated podcast library on a local loopback URL."""

from __future__ import annotations

import argparse
import functools
import http.server
import webbrowser
from pathlib import Path


class PreviewHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def make_server(directory: Path, host: str, port: int) -> http.server.ThreadingHTTPServer:
    root = directory.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"site directory does not exist: {root}")
    if not (root / "index.html").is_file():
        raise FileNotFoundError(f"site index is missing: {root / 'index.html'}")
    handler = functools.partial(PreviewHandler, directory=str(root))
    return http.server.ThreadingHTTPServer((host, port), handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="Generated podcast-library directory")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address; defaults to loopback only")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true", help="Open the preview URL in the default browser")
    args = parser.parse_args()

    server = make_server(Path(args.directory), args.host, args.port)
    address, port = server.server_address[:2]
    display_host = "127.0.0.1" if address in {"0.0.0.0", "::"} else address
    url = f"http://{display_host}:{port}/"
    print(f"PennyScribe library: {url}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPreview server stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
