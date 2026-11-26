#!/usr/bin/env python3
"""Serve assets/shared/flip7.html locally:  python3 web/server.py [port=8080]
Static files only, for local testing of the Mini App page: it does NOT serve
the /api/* endpoints, so synced play through it does not work (the live Mini
App is served by bot.py itself on :8080). There is no /web or /play command;
the Mini App is opened from a board's Mini App button or /games. Telegram
Mini Apps require an HTTPS URL, so expose the bot with a tunnel (e.g.
`cloudflare tunnel` / ngrok https) and set FLIP7_WEB_URL to the tunnel URL.

Only files under assets/ are served (plus / and /flip7.html, which serve
the shared shell) so the rest of the repo is never exposed.
"""
import http.server
import os
import sys
import urllib.parse

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
print(f"Serving flip7.html at http://localhost:{PORT}/assets/shared/flip7.html")


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/flip7.html"):
            self.path = "/assets/shared/flip7.html"
            path = self.path
        if not path.startswith("/assets/"):
            self.send_error(404, "not found")
            return
        super().do_GET()


http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
