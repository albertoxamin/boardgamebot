#!/usr/bin/env python3
"""Serve assets/shared/flip7.html locally:  python3 web/server.py [port=8080]
Telegram Mini Apps / HTML5 Games require an HTTPS URL, so expose this
with a tunnel (e.g. `cloudflare tunnel` / ngrok https) and set:
  FLIP7_WEB_URL=https://<tunnel>/assets/shared/flip7.html  (for /web Mini App)
  FLIP7_GAME_URL=https://<tunnel>/assets/shared/flip7.html (for /play sendGame)
  FLIP7_GAME_SHORT_NAME=<short name from @BotFather /newgame>
Restart bot.py after setting them. Without a tunnel, /web sends the
HTML file itself via sendDocument - that always works.

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
