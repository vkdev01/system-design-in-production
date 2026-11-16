#!/usr/bin/env python3
"""Render every page in a headless browser and assert each Mermaid diagram
produced an SVG.

A diagram with a syntax error still produces markup, so counting `.mermaid`
nodes is not enough -- Mermaid renders a red error box instead of an SVG, and
that is what this checks for.

    python site_builder/check_diagrams.py [dist]
"""

from __future__ import annotations

import functools
import http.server
import re
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "dist").resolve()


def chrome() -> str:
    for name in ("google-chrome", "chromium", "chromium-browser", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found
    sys.exit("no headless browser found (google-chrome or chromium)")


def main() -> None:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    server = socketserver.ThreadingTCPServer(
        ("127.0.0.1", port), functools.partial(Quiet, directory=str(ROOT))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.5)

    browser = chrome()
    total, broken = 0, []
    for page in sorted(ROOT.rglob("index.html")):
        rel = page.parent.relative_to(ROOT).as_posix()
        dom = subprocess.run(
            [browser, "--headless", "--disable-gpu", "--no-sandbox",
             "--virtual-time-budget=9000", "--dump-dom",
             f"http://127.0.0.1:{port}/{rel}/"],
            capture_output=True, text=True,
        ).stdout
        nodes = dom.count('class="mermaid"')
        if not nodes:
            continue
        total += nodes
        svgs = len(re.findall(r'<pre class="mermaid"[^>]*>\s*<svg', dom))
        syntax = dom.count("Syntax error")
        if svgs != nodes or syntax:
            broken.append(rel)
            print(f"BROKEN {rel}: {nodes} diagrams, {svgs} svg, {syntax} syntax errors")

    server.shutdown()
    print(f"diagrams checked: {total}, broken pages: {len(broken)}")
    sys.exit(1 if broken else 0)


if __name__ == "__main__":
    main()
