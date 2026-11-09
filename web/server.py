#!/usr/bin/env python3
"""Serve web/flip7.html locally:  python3 web/server.py [port=8080]
Telegram Mini Apps / HTML5 Games require an HTTPS URL, so expose this
with a tunnel (e.g. `cloudflare tunnel` / ngrok https) and set:
  FLIP7_WEB_URL=https://<tunnel>/flip7.html          (for /web Mini App)
  FLIP7_GAME_URL=https://<tunnel>/flip7.html         (for /play sendGame)
  FLIP7_GAME_SHORT_NAME=<short name from @BotFather /newgame>
Restart bot.py after setting them. Without a tunnel, /web sends the
HTML file itself via sendDocument - that always works.
"""
import http.server, os, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
os.chdir(os.path.dirname(os.path.abspath(__file__)))
print(f"Serving flip7.html at http://localhost:{PORT}/flip7.html")
http.server.ThreadingHTTPServer(("0.0.0.0", PORT),
                                http.server.SimpleHTTPRequestHandler).serve_forever()
