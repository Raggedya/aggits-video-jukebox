from __future__ import annotations

import http.server
import socket
import threading
from pathlib import Path


class PreviewServer:
    def __init__(self) -> None:
        self.server: http.server.ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.root: Path | None = None

    def start(self, root: Path) -> str:
        self.stop()
        self.root = root.resolve()

        directory = str(self.root)

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=directory, **kwargs)

            def log_message(self, format: str, *args: object) -> None:
                return

            def send_head(self):
                # Old tabs/bookmarks may still use the numeric loopback URL.
                # Redirect before loading YouTube so its origin/referrer agree.
                host = self.headers.get("Host", "").split(":", 1)[0]
                if host == "127.0.0.1":
                    self.send_response(302)
                    self.send_header("Location", f"http://localhost:{self.server.server_port}{self.path}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return None
                return super().send_head()

            def end_headers(self) -> None:
                self.send_header("Cache-Control", "no-store")
                super().end_headers()

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        # YouTube rejects some embed contexts using a numeric loopback origin.
        # Keep binding loopback only; expose the browser-friendly hostname.
        return f"http://localhost:{port}/"

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        self.server = None
        self.thread = None
